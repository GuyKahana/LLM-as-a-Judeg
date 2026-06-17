"""Batch runner – orchestrates log listing, evaluation, and verdict writing."""

from __future__ import annotations

import json
import logging
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Optional

from llm_judge.config import Settings
from llm_judge.evaluator import evaluate_turn
from llm_judge.golden_examples import load_golden_examples
from llm_judge.llm_client import LLMClient
from llm_judge.log_parser import parse_log
from llm_judge.models import BlobMeta, FlaggedItem, RunSummary, Verdict
from llm_judge.rubrics.registry import get_golden_type, get_rubric_content, get_rubric_name
from llm_judge.storage.client import StorageClient

logger = logging.getLogger(__name__)


def _evaluate_one(
    blob: BlobMeta,
    storage_client: StorageClient,
    llm_client: LLMClient,
    config: Settings,
    rubric_name: str,
    run_id: str = "",
) -> Verdict:
    """Download, parse, and evaluate a single log blob. Called from a worker thread."""
    raw_json = storage_client.read_log(blob.case_id, blob.filename)
    parsed_turn = parse_log(raw_json, blob.filename, blob.case_id)
    rubric_content = get_rubric_content(rubric_name)
    golden_type = get_golden_type(blob.filename) or rubric_name
    logger.info(
        "Evaluating %s/%s with rubric=%s golden_type=%s",
        blob.case_id, blob.filename, rubric_name, golden_type,
    )
    golden_examples = load_golden_examples(storage_client, golden_type)
    verdict = evaluate_turn(
        parsed_turn=parsed_turn,
        rubric_content=rubric_content,
        golden_examples=golden_examples,
        llm_client=llm_client,
        config=config,
        prompt_type=rubric_name,
    )
    verdict.run_id = run_id
    return verdict


def run_batch(
    config: Settings,
    case_id: Optional[str] = None,
    lookback_hours_override: Optional[int] = None,
    dry_run_override: bool = False,
) -> RunSummary:
    """Execute one full judge batch run and return a RunSummary.

    Parameters
    ----------
    config:
        Fully-populated Settings instance.
    case_id:
        When provided, evaluate ALL logs for this case regardless of age.
        ``--lookback-hours`` / ``JUDGE_LOOKBACK_HOURS`` is ignored entirely.
    lookback_hours_override:
        Override ``config.judge_lookback_hours`` for this run.
        Ignored when ``case_id`` is set.
    dry_run_override:
        When True, skip writing verdicts and sending alerts.
        Merged with ``config.dry_run`` (either flag enables dry-run).
    """
    run_id = str(uuid.uuid4())
    started_at = datetime.now(tz=timezone.utc)
    effective_dry_run = dry_run_override or config.dry_run

    logger.info(
        "Starting batch run",
        extra={
            "run_id": run_id,
            "case_id": case_id,
            "dry_run": effective_dry_run,
            "lookback_hours_override": lookback_hours_override,
        },
    )

    storage_client = StorageClient(config)
    llm_client = LLMClient(config)

    # ------------------------------------------------------------------
    # 1. List logs
    # ------------------------------------------------------------------
    if case_id:
        logger.info(
            "Listing all logs for case_id=%s (lookback ignored)", case_id,
            extra={"run_id": run_id}
        )
        blobs: list[BlobMeta] = list(storage_client.list_all_logs_for_case(case_id))
    else:
        effective_lookback = lookback_hours_override or config.judge_lookback_hours
        logger.info(
            "Listing logs modified in last %d hours", effective_lookback,
            extra={"run_id": run_id}
        )
        blobs = list(storage_client.list_logs_modified_since(effective_lookback))

    total_logs = len(blobs)
    logger.info("Found %d total log blobs", total_logs, extra={"run_id": run_id})

    # ------------------------------------------------------------------
    # 2. Pre-filter: skip existing verdicts and unmapped filenames
    # ------------------------------------------------------------------
    skipped_existing = 0
    unmapped = 0
    work_items: list[tuple[BlobMeta, str]] = []  # (blob, rubric_name)

    for blob in blobs:
        rubric_name = get_rubric_name(blob.filename)
        if rubric_name is None:
            logger.debug(
                "No rubric for filename=%s case_id=%s – skipping",
                blob.filename, blob.case_id,
            )
            unmapped += 1
            continue
        if storage_client.verdict_exists(blob.case_id, blob.filename):
            logger.debug(
                "Verdict already exists for %s/%s – skipping",
                blob.case_id, blob.filename,
            )
            skipped_existing += 1
            continue
        work_items.append((blob, rubric_name))

    # ------------------------------------------------------------------
    # 3. Cap to JUDGE_MAX_TURNS_PER_RUN
    # ------------------------------------------------------------------
    if len(work_items) > config.judge_max_turns_per_run:
        logger.warning(
            "Capping work items from %d to %d (JUDGE_MAX_TURNS_PER_RUN)",
            len(work_items), config.judge_max_turns_per_run,
            extra={"run_id": run_id},
        )
        work_items = work_items[: config.judge_max_turns_per_run]

    # ------------------------------------------------------------------
    # 4. Evaluate with ThreadPoolExecutor
    # ------------------------------------------------------------------
    evaluated = 0
    flagged = 0
    errors = 0
    parse_errors = 0
    by_prompt_type: dict[str, int] = {}
    flagged_items: list[FlaggedItem] = []

    futures: dict = {}
    with ThreadPoolExecutor(max_workers=config.judge_max_workers) as executor:
        for blob, rubric_name in work_items:
            future = executor.submit(
                _evaluate_one, blob, storage_client, llm_client, config, rubric_name, run_id
            )
            futures[future] = (blob, rubric_name)

        for future in as_completed(futures):
            blob, rubric_name = futures[future]
            try:
                verdict: Verdict = future.result()
            except Exception as exc:
                logger.error(
                    "Unhandled exception evaluating %s/%s: %s",
                    blob.case_id, blob.filename, exc,
                    exc_info=True,
                    extra={"run_id": run_id},
                )
                errors += 1
                continue

            evaluated += 1

            # Track per-prompt-type counts
            by_prompt_type[rubric_name] = by_prompt_type.get(rubric_name, 0) + 1

            if verdict.parse_error:
                parse_errors += 1
                logger.warning(
                    "Parse error for %s/%s", blob.case_id, blob.filename,
                    extra={"run_id": run_id},
                )
            elif verdict.flagged:
                flagged += 1
                flagged_items.append(
                    FlaggedItem(
                        case_id=verdict.case_id,
                        filename=verdict.filename,
                        prompt_type=verdict.prompt_type,
                        score=verdict.score,
                        reasoning_snippet=verdict.reasoning[:200],
                    )
                )

            # Write verdict unless dry run
            if not effective_dry_run:
                try:
                    storage_client.write_verdict(
                        blob.case_id, blob.filename, verdict.model_dump(mode="json")
                    )
                except Exception as write_exc:
                    logger.error(
                        "Failed to write verdict for %s/%s: %s",
                        blob.case_id, blob.filename, write_exc,
                        extra={"run_id": run_id},
                    )
                    errors += 1

    finished_at = datetime.now(tz=timezone.utc)

    summary = RunSummary(
        run_id=run_id,
        started_at=started_at,
        finished_at=finished_at,
        total_logs=total_logs,
        evaluated=evaluated,
        skipped_existing=skipped_existing,
        unmapped=unmapped,
        flagged=flagged,
        errors=errors,
        parse_errors=parse_errors,
        by_prompt_type=by_prompt_type,
        flagged_items=flagged_items,
    )

    logger.info(
        "Batch run complete",
        extra={"run_id": run_id, "summary": summary.model_dump(mode="json")},
    )

    # Persist RunSummary to storage (skip on dry run)
    if not effective_dry_run:
        run_summary_path = f"{config.runs_prefix}{run_id}.json"
        try:
            storage_client._verdict.write_file(
                run_summary_path,
                json.dumps(summary.model_dump(mode="json"), default=str, indent=2),
            )
            logger.debug("Wrote run summary to %s", run_summary_path)
        except Exception as summary_exc:
            logger.error(
                "Failed to write run summary for run_id=%s: %s",
                run_id, summary_exc,
                extra={"run_id": run_id},
            )

    return summary
