"""Click CLI entry points for the LLM Judge service."""

from __future__ import annotations

import json
import sys

import click

from llm_judge.alerts import send_digest
from llm_judge.config import Settings
from llm_judge.golden_examples import load_golden_examples
from llm_judge.llm_client import LLMClient
from llm_judge.log_parser import parse_log
from llm_judge.logging_setup import setup_logging
from llm_judge.models import RunSummary
from llm_judge.rubrics.registry import get_rubric_content, get_rubric_name, list_rubrics
from llm_judge.runner import run_batch
from llm_judge.storage.client import StorageClient


@click.group()
@click.option("--log-level", default="INFO", show_default=True, help="Logging level.")
def cli(log_level: str) -> None:
    """LLM-as-a-Judge batch service for evaluating prompt-turn logs."""
    setup_logging(level=log_level)


@cli.command()
@click.option(
    "--case-id",
    default=None,
    help=(
        "Evaluate all logs for a specific case ID. "
        "Ignores --lookback-hours entirely — all logs for the case are evaluated "
        "regardless of age."
    ),
)
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="Evaluate without writing verdicts or sending alerts.",
)
@click.option(
    "--lookback-hours",
    default=None,
    type=int,
    help=(
        "Override JUDGE_LOOKBACK_HOURS for this run. "
        "Ignored when --case-id is set."
    ),
)
def run(case_id: str | None, dry_run: bool, lookback_hours: int | None) -> None:
    """Run a batch evaluation job."""
    config = Settings()  # type: ignore[call-arg]
    summary: RunSummary = run_batch(
        config=config,
        case_id=case_id,
        lookback_hours_override=lookback_hours,
        dry_run_override=dry_run,
    )
    send_digest(summary=summary, config=config, dry_run=dry_run)
    # Exit non-zero if there were errors
    if summary.errors > 0:
        sys.exit(1)


@cli.command()
def calibrate() -> None:
    """Run judge over all golden examples and report drift.

    Goldens are always positive examples (expected_verdict = "pass").
    Any golden that scores <= JUDGE_SCORE_THRESHOLD is flagged as judge drift.
    """
    setup_logging()
    config = Settings()  # type: ignore[call-arg]
    storage_client = StorageClient(config)
    llm_client = LLMClient(config)

    from llm_judge.evaluator import evaluate_turn

    # Collect all distinct rubric names from the registry
    rubric_names = sorted({name for _, name in list_rubrics()})

    drift_count = 0
    total_checked = 0

    for rubric_name in rubric_names:
        examples = load_golden_examples(storage_client, rubric_name)
        if not examples:
            click.echo(f"[{rubric_name}] No golden examples found – skipping.")
            continue

        rubric_content = get_rubric_content(rubric_name)

        for i, example in enumerate(examples, start=1):
            # Parse the golden JSON as if it were a regular log
            parsed = parse_log(
                raw_json=example,
                filename=f"golden_{rubric_name}_{i}.json",
                case_id="calibration",
            )
            verdict = evaluate_turn(
                parsed_turn=parsed,
                rubric_content=rubric_content,
                golden_examples=[],  # Don't use goldens to evaluate goldens
                llm_client=llm_client,
                config=config,
                prompt_type=rubric_name,
            )
            total_checked += 1
            status: str
            if verdict.parse_error:
                status = "PARSE_ERROR"
                drift_count += 1
            elif verdict.score is not None and verdict.score <= config.judge_score_threshold:
                status = f"DRIFT (score={verdict.score} <= threshold={config.judge_score_threshold})"
                drift_count += 1
            else:
                status = f"OK (score={verdict.score})"

            click.echo(f"[{rubric_name}] golden_{i}: {status}")
            if verdict.reasoning:
                click.echo(f"  reasoning: {verdict.reasoning[:200]}")

    click.echo(f"\nCalibration complete: {total_checked} golden(s) checked, {drift_count} drift(s) detected.")
    if drift_count > 0:
        sys.exit(1)


@cli.command("list-rubrics")
def list_rubrics_cmd() -> None:
    """Print all filename pattern -> rubric name mappings."""
    rows = list_rubrics()
    max_pattern_len = max(len(p) for p, _ in rows) if rows else 20
    click.echo(f"{'Pattern':<{max_pattern_len}}  Rubric Name")
    click.echo("-" * (max_pattern_len + 20))
    for pattern, name in rows:
        click.echo(f"{pattern:<{max_pattern_len}}  {name}")
