"""View 2 — Run detail."""

from __future__ import annotations

from datetime import datetime

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


def _find_run(run_id: str | None, case_id: str | None) -> dict | None:
    """Locate a run dict by run_id or by case_id (synthetic)."""
    runs = data.load_runs()
    if run_id:
        for r in runs:
            if r.get("run_id") == run_id:
                return r
    if case_id:
        for r in runs:
            if r.get("case_id") == case_id:
                return r
    if runs:
        return runs[0]
    return None


def render() -> None:
    run_id: str | None = st.session_state.get("selected_run_id")
    case_id: str | None = st.session_state.get("selected_case_id")

    if st.button("← Back to Runs"):
        st.session_state["current_view"] = "Runs"
        st.rerun()

    with st.spinner("Loading run…"):
        run = _find_run(run_id, case_id)

    if run is None:
        st.warning("No run selected. Go back to the Runs list and click a row.")
        return

    rid = run.get("run_id", "")
    is_synthetic = run.get("synthetic", False)
    title = f"Run: `{rid[:16]}…`" if len(rid) > 16 else f"Run: `{rid}`"
    if is_synthetic:
        title = f"Case: {run.get('case_id', '')}"
    st.subheader(title)

    # ------------------------------------------------------------------
    # 5 metric cards
    # ------------------------------------------------------------------
    evaluated = run.get("evaluated", 0)
    flagged = run.get("flagged", 0)
    flagged_pct = round(100 * flagged / evaluated, 1) if evaluated else 0.0
    parse_errors = run.get("parse_errors", 0)
    duration = _duration_str(run.get("started_at"), run.get("finished_at"))

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Evaluated", evaluated)
    c2.metric("Flagged", flagged)
    c3.metric("Flagged %", f"{flagged_pct}%")
    c4.metric("Parse Errors", parse_errors)
    c5.metric("Duration", duration)

    st.divider()

    # ------------------------------------------------------------------
    # By-prompt-type bar chart
    # ------------------------------------------------------------------
    by_prompt = run.get("by_prompt_type") or {}
    if by_prompt:
        import pandas as pd

        st.subheader("Evaluations by Prompt Type")
        df_pt = pd.DataFrame(
            {"Prompt Type": list(by_prompt.keys()), "Count": list(by_prompt.values())}
        ).set_index("Prompt Type")
        st.bar_chart(df_pt)

    # ------------------------------------------------------------------
    # Score distribution (derive from verdicts for this run/case)
    # ------------------------------------------------------------------
    st.subheader("Score Distribution")
    with st.spinner("Loading verdicts for score chart…"):
        filter_case = run.get("case_id")
        verdicts = data.load_verdicts(case_id=filter_case)
        if not filter_case:
            # Non-synthetic run: filter by run_id if available
            verdicts = [v for v in verdicts if v.get("run_id") == rid] if rid else verdicts

    score_counts: dict[int, int] = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
    for v in verdicts:
        s = v.get("score")
        if isinstance(s, int) and 1 <= s <= 5:
            score_counts[s] += 1

    if any(score_counts.values()):
        import pandas as pd

        df_sc = pd.DataFrame(
            {"Score": list(score_counts.keys()), "Count": list(score_counts.values())}
        ).set_index("Score")
        st.bar_chart(df_sc)
    else:
        st.caption("No score data available.")

    st.divider()

    # ------------------------------------------------------------------
    # Flagged items table
    # ------------------------------------------------------------------
    flagged_items = run.get("flagged_items") or []
    st.subheader(f"Flagged Items ({len(flagged_items)})")
    if flagged_items:
        import pandas as pd

        rows = []
        for fi in flagged_items:
            rows.append(
                {
                    "Case ID": fi.get("case_id", ""),
                    "Filename": fi.get("filename", ""),
                    "Prompt Type": fi.get("prompt_type", ""),
                    "Score": fi.get("score", ""),
                    "Reasoning Snippet": fi.get("reasoning_snippet", ""),
                }
            )
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    else:
        st.success("No flagged items in this run.")

    st.divider()

    # Navigation button to Verdicts Explorer filtered to this case
    if st.button("Open in Verdicts Explorer"):
        if filter_case:
            st.session_state["filter_case_id"] = [filter_case]
        st.session_state["current_view"] = "Verdicts Explorer"
        st.rerun()
