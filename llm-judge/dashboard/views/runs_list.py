"""View 1 — Runs list."""

from __future__ import annotations

from datetime import datetime, timezone

import streamlit as st

from dashboard import data


def _parse_dt(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return None


def _duration_str(started: str | None, finished: str | None) -> str:
    s = _parse_dt(started)
    f = _parse_dt(finished)
    if s is None or f is None:
        return "—"
    secs = int((f - s).total_seconds())
    if secs < 60:
        return f"{secs}s"
    if secs < 3600:
        return f"{secs // 60}m {secs % 60}s"
    return f"{secs // 3600}h {(secs % 3600) // 60}m"


def _fmt_dt(s: str | None) -> str:
    dt = _parse_dt(s)
    if dt is None:
        return "—"
    return dt.strftime("%Y-%m-%d %H:%M UTC")


def render() -> None:
    st.header("Runs")

    with st.spinner("Loading runs…"):
        runs = data.load_runs()

    if not runs:
        st.info("No runs found. Use the **Trigger** tab to start a batch evaluation.")
        return

    # Build table rows
    rows = []
    for r in runs:
        evaluated = r.get("evaluated", 0)
        flagged = r.get("flagged", 0)
        flagged_pct = round(100 * flagged / evaluated, 1) if evaluated else 0.0
        run_id = r.get("run_id", "")
        label = run_id[:8] + "…" if len(run_id) > 8 else run_id
        if r.get("synthetic"):
            label = f"[synth] {r.get('case_id', '')}"

        rows.append(
            {
                "Run ID": label,
                "Started": _fmt_dt(r.get("started_at")),
                "Duration": _duration_str(r.get("started_at"), r.get("finished_at")),
                "Case ID": r.get("case_id", "—"),
                "Evaluated": evaluated,
                "Flagged": flagged,
                "Flagged %": f"{flagged_pct}%",
                "Errors": r.get("errors", 0),
                "Parse Errors": r.get("parse_errors", 0),
                "_run_id": run_id,  # hidden, used for navigation
            }
        )

    import pandas as pd

    df = pd.DataFrame(rows)
    display_cols = [c for c in df.columns if not c.startswith("_")]

    st.caption(f"{len(rows)} run(s) shown — click a row to open Run Detail")

    event = st.dataframe(
        df[display_cols],
        use_container_width=True,
        hide_index=True,
        on_select="rerun",
        selection_mode="single-row",
    )

    selected_rows = event.selection.rows if event.selection else []
    if selected_rows:
        idx = selected_rows[0]
        selected_run = runs[idx]
        st.session_state["selected_run_id"] = selected_run.get("run_id")
        st.session_state["selected_case_id"] = selected_run.get("case_id")
        st.session_state["current_view"] = "Run Detail"
        st.rerun()
