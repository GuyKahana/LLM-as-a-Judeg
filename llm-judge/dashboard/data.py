"""Data loading layer for the LLM Judge dashboard.

All storage reads go through this module. Results are cached with st.cache_data.
"""

from __future__ import annotations

import json
import logging
import sys
from collections import defaultdict
from pathlib import Path
from typing import Optional

import streamlit as st

# Ensure llm_judge (src/) is importable when data.py is imported before app.py
# has had a chance to fix sys.path (e.g. during hot-reload or direct import).
_src_dir = str(Path(__file__).parent.parent / "src")
if _src_dir not in sys.path:
    sys.path.insert(0, _src_dir)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Lazy config / client construction — done once per session, not per call.
# ---------------------------------------------------------------------------

@st.cache_resource
def _get_storage_client():
    """Return a StorageClient built from Settings(). Cached for the session."""
    from llm_judge.config import Settings
    from llm_judge.storage.client import StorageClient

    config = Settings()  # type: ignore[call-arg]
    return StorageClient(config), config


# ---------------------------------------------------------------------------
# Public data-loading functions
# ---------------------------------------------------------------------------


def runs_location_hint() -> str:
    """Human-readable description of where run summaries are expected to live."""
    _client, config = _get_storage_client()
    base = ""
    if config.verdict_storage_provider == "local":
        base = f"{config.local_storage_base_dir}/"
    return (
        f"{base}{config.verdict_bucket}/{config.runs_prefix} "
        f"(provider: {config.verdict_storage_provider})"
    )


@st.cache_data(ttl=30)
def load_runs() -> list[dict]:
    """Load all run summary files from {verdict_bucket}/{runs_prefix}*.json.

    Returns a list of run dicts, newest first.
    If no run files exist, synthesises a RunSummary-like dict per case_id
    from verdict files and flags those with ``"synthetic": True``.
    """
    client, config = _get_storage_client()
    runs: list[dict] = []

    try:
        for path, mtime in client._verdict.list_files(config.runs_prefix):
            if not path.endswith(".json"):
                continue
            try:
                raw = client._verdict.read_file(path)
                data = json.loads(raw)
                data.setdefault("synthetic", False)
                runs.append(data)
            except Exception as exc:
                logger.warning("Failed to read run file %s: %s", path, exc)
    except Exception as exc:
        logger.warning("Failed to list run files: %s", exc)

    if runs:
        # Sort newest first by started_at
        runs.sort(key=lambda r: r.get("started_at", ""), reverse=True)
        return runs

    # Fallback: synthesise from verdicts
    logger.info("No persisted runs found — synthesising from verdicts")
    return _synthesise_runs_from_verdicts(client, config)


@st.cache_data(ttl=30)
def load_verdicts(case_id: Optional[str] = None) -> list[dict]:
    """Load all verdict JSON files, optionally filtered by case_id.

    Returns a list of verdict dicts.
    """
    client, config = _get_storage_client()
    verdicts: list[dict] = []

    prefix = config.verdict_prefix
    if case_id:
        prefix = f"{config.verdict_prefix}{case_id}/"

    try:
        for path, _mtime in client._verdict.list_files(prefix):
            if not path.endswith(".json"):
                continue
            # Skip run summary files stored alongside verdicts
            filename = path.split("/")[-1]
            if not filename:
                continue
            # Run summaries live under runs/ prefix — not under verdict_prefix
            try:
                raw = client._verdict.read_file(path)
                data = json.loads(raw)
                # Only include dicts that look like verdicts (have case_id + filename)
                if "case_id" in data and "filename" in data and "prompt_type" in data:
                    verdicts.append(data)
            except Exception as exc:
                logger.warning("Failed to read verdict %s: %s", path, exc)
    except Exception as exc:
        logger.warning("Failed to list verdicts: %s", exc)

    return verdicts


@st.cache_data(ttl=30)
def load_source_log(case_id: str, filename: str) -> Optional[dict]:
    """Read the production log for a given case_id + filename.

    Returns None (not an error) if the log is missing.
    """
    client, _config = _get_storage_client()
    try:
        return client.read_log(case_id, filename)
    except Exception as exc:
        logger.info("Source log not available for %s/%s: %s", case_id, filename, exc)
        return None


def local_run_env() -> dict[str, str]:
    """Return an environment dict that forces a runner subprocess fully local.

    A local run must read logs, write verdicts, AND read goldens from the local
    filesystem — co-location (see CONTEXT.md). Because per-root provider
    overrides win over ``STORAGE_PROVIDER`` in :class:`Settings`, we have to pin
    *all four* variables, otherwise a hybrid ``.env`` (e.g.
    ``PRODUCTION_STORAGE_PROVIDER=gcs``) would leak the run back to the cloud.
    """
    import os

    env = os.environ.copy()
    env["STORAGE_PROVIDER"] = "local"
    env["PRODUCTION_STORAGE_PROVIDER"] = "local"
    env["VERDICT_STORAGE_PROVIDER"] = "local"
    env["GOLDEN_STORAGE_PROVIDER"] = "local"
    return env


def _production_provider(source: str):
    """Return the StorageProvider to search for production logs.

    ``source="cloud"`` uses the configured production root (GCS in a hybrid
    setup). ``source="local"`` builds a LocalStorageProvider rooted at
    ``<LOCAL_STORAGE_BASE_DIR>/<PRODUCTION_BUCKET>``, independent of
    ``PRODUCTION_STORAGE_PROVIDER`` — so the UI can browse local test cases
    while real runs still read from the cloud.
    """
    client, config = _get_storage_client()
    if source == "local":
        from llm_judge.storage.factory import create_provider

        return create_provider(config.production_bucket, config, "local")
    return client._prod


@st.cache_data(ttl=30)
def list_cases(source: str = "cloud") -> list[str]:
    """List distinct case_id directories under ``logs/`` for *source*.

    Falls back to extracting case_ids from verdicts if listing fails.
    """
    provider = _production_provider(source)

    try:
        seen: set[str] = set()
        for path, _mtime in provider.list_files("logs/"):
            parts = path.split("/")
            if len(parts) >= 3:  # must be logs/{case_id}/{filename}
                candidate = parts[1]
                if candidate and not candidate.startswith("."):
                    seen.add(candidate)
        if seen:
            return sorted(seen)
    except Exception as exc:
        logger.warning("Could not list %s logs: %s", source, exc)

    if source == "local":
        return []  # no verdict fallback for local browsing

    # Fallback: derive from verdicts
    verdicts = load_verdicts()
    return sorted({v["case_id"] for v in verdicts if v.get("case_id")})


@st.cache_data(ttl=30)
def lookup_case_files(case_id: str, source: str = "cloud") -> list[str]:
    """Return the sorted log filenames for *case_id* under *source*.

    Used by the Trigger view to verify a typed case ID exists (and show what
    will be evaluated) before launching a run. An empty list means the case was
    not found under ``logs/{case_id}/``. ``source`` is ``"cloud"`` (the
    configured production root) or ``"local"`` (the local filesystem).
    """
    provider = _production_provider(source)
    prefix = f"logs/{case_id}/"
    files = [path.split("/")[-1] for path, _mtime in provider.list_files(prefix)]
    return sorted(f for f in files if f)


def upload_case_logs(case_id: str, files: list[tuple[str, bytes]]) -> list[str]:
    """Write uploaded log files to the LOCAL production root under logs/{case_id}/.

    Upload Case is a local-testing tool: cases are always written to the local
    filesystem (regardless of PRODUCTION_STORAGE_PROVIDER), so the subsequent
    all-local "Run judge" reads exactly these files and the case is browsable
    via the Trigger view's "Local files" source.

    *files* is a list of (filename, raw_bytes) pairs.
    Returns the list of filenames that were written successfully.
    """
    provider = _production_provider("local")
    written: list[str] = []
    for filename, content in files:
        path = f"logs/{case_id}/{filename}"
        provider.write_file(path, content.decode("utf-8"))
        written.append(filename)
    # Invalidate case list cache so the new case appears immediately
    list_cases.clear()
    return written


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _synthesise_runs_from_verdicts(client, config) -> list[dict]:
    """Build fake RunSummary-like dicts grouped by case_id from verdict files."""
    verdicts = load_verdicts()
    by_case: dict[str, list[dict]] = defaultdict(list)
    for v in verdicts:
        by_case[v.get("case_id", "unknown")].append(v)

    synthetic_runs: list[dict] = []
    for cid, vs in by_case.items():
        evaluated = len(vs)
        flagged = sum(1 for v in vs if v.get("flagged"))
        parse_errors = sum(1 for v in vs if v.get("parse_error"))
        by_prompt: dict[str, int] = defaultdict(int)
        for v in vs:
            pt = v.get("prompt_type", "unknown")
            by_prompt[pt] += 1

        timestamps = [v.get("evaluated_at", "") for v in vs if v.get("evaluated_at")]
        started = min(timestamps) if timestamps else ""
        finished = max(timestamps) if timestamps else ""

        flagged_items = [
            {
                "case_id": v["case_id"],
                "filename": v["filename"],
                "prompt_type": v.get("prompt_type", ""),
                "score": v.get("score"),
                "reasoning_snippet": (v.get("reasoning") or "")[:200],
            }
            for v in vs
            if v.get("flagged")
        ]

        synthetic_runs.append(
            {
                "run_id": f"synthetic-{cid}",
                "started_at": started,
                "finished_at": finished,
                "total_logs": evaluated,
                "evaluated": evaluated,
                "skipped_existing": 0,
                "unmapped": 0,
                "flagged": flagged,
                "errors": 0,
                "parse_errors": parse_errors,
                "by_prompt_type": dict(by_prompt),
                "flagged_items": flagged_items,
                "case_id": cid,
                "synthetic": True,
            }
        )

    synthetic_runs.sort(key=lambda r: r.get("started_at", ""), reverse=True)
    return synthetic_runs
