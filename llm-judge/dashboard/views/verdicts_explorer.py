"""View 3 — Verdicts explorer."""

from __future__ import annotations

import streamlit as st

from dashboard import data

# Score colour mapping
_SCORE_COLOURS = {
    5: "🟢",
    4: "🟢",
    3: "🟡",
    2: "🔴",
    1: "🔴",
}


def _score_badge(v: dict) -> str:
    if v.get("parse_error"):
        return "⬜ PARSE ERR"
    score = v.get("score")
    if score is None:
        return "⬜ —"
    return f"{_SCORE_COLOURS.get(score, '⬜')} {score}"


def render() -> None:
    st.header("Verdicts Explorer")

    with st.spinner("Loading verdicts…"):
        all_verdicts = data.load_verdicts()

    if not all_verdicts:
        st.info("No verdicts found.")
        return

    # ------------------------------------------------------------------
    # Sidebar / expander filters
    # ------------------------------------------------------------------
    with st.expander("Filters", expanded=True):
        col1, col2 = st.columns(2)

        all_cases = sorted({v.get("case_id", "") for v in all_verdicts if v.get("case_id")})
        all_prompt_types = sorted({v.get("prompt_type", "") for v in all_verdicts if v.get("prompt_type")})
        all_schema_variants = sorted({v.get("schema_variant", "") for v in all_verdicts if v.get("schema_variant")})

        # Pre-populate from session state if navigated from Run Detail
        default_cases = st.session_state.pop("filter_case_id", [])

        with col1:
            sel_cases = st.multiselect(
                "Case ID",
                options=all_cases,
                default=[c for c in default_cases if c in all_cases],
            )
            sel_prompt_types = st.multiselect("Prompt Type", options=all_prompt_types)
            sel_schema_variants = st.multiselect("Schema Variant", options=all_schema_variants)

        with col2:
            flagged_filter = st.radio(
                "Flagged",
                options=["All", "Flagged only", "Not flagged"],
                horizontal=True,
            )
            score_min, score_max = st.slider(
                "Score range", min_value=1, max_value=5, value=(1, 5)
            )
            search_text = st.text_input("Search reasoning (case-insensitive)")

    # ------------------------------------------------------------------
    # Apply filters
    # ------------------------------------------------------------------
    filtered = all_verdicts

    if sel_cases:
        filtered = [v for v in filtered if v.get("case_id") in sel_cases]
    if sel_prompt_types:
        filtered = [v for v in filtered if v.get("prompt_type") in sel_prompt_types]
    if sel_schema_variants:
        filtered = [v for v in filtered if v.get("schema_variant") in sel_schema_variants]

    if flagged_filter == "Flagged only":
        filtered = [v for v in filtered if v.get("flagged")]
    elif flagged_filter == "Not flagged":
        filtered = [v for v in filtered if not v.get("flagged")]

    # Score range (exclude parse_error verdicts from score filter so they still appear)
    filtered = [
        v for v in filtered
        if v.get("parse_error")
        or (
            isinstance(v.get("score"), int)
            and score_min <= v["score"] <= score_max
        )
        or (v.get("score") is None and not v.get("parse_error"))
    ]

    if search_text:
        lower = search_text.lower()
        filtered = [v for v in filtered if lower in (v.get("reasoning") or "").lower()]

    st.caption(f"Showing {len(filtered)} of {len(all_verdicts)} verdicts")

    if not filtered:
        st.info("No verdicts match the current filters.")
        return

    # ------------------------------------------------------------------
    # Table + expandable rows
    # ------------------------------------------------------------------
    for v in filtered:
        score_label = _score_badge(v)
        flagged_icon = "🚩" if v.get("flagged") else ""
        header = (
            f"{score_label}  {flagged_icon}  **{v.get('prompt_type', '—')}** "
            f"| {v.get('schema_variant', '—')} "
            f"| `{v.get('filename', '—')}` "
            f"| {v.get('case_id', '—')}"
        )

        with st.expander(header, expanded=False):
            # Evaluated at
            evaluated_at = v.get("evaluated_at", "")
            if evaluated_at:
                st.caption(f"Evaluated at: {evaluated_at}")

            # Parse error banner
            if v.get("parse_error"):
                st.error("Parse error — LLM response could not be parsed.")
                raw = v.get("raw_response")
                if raw:
                    st.code(raw, language=None)
            else:
                # Score + per_criterion
                score = v.get("score")
                per_crit = v.get("per_criterion") or {}
                if score is not None:
                    st.write(f"**Score:** {score}/5")
                if per_crit:
                    import pandas as pd
                    crit_df = pd.DataFrame(
                        [{"Criterion": k, "Score": val} for k, val in per_crit.items()]
                    )
                    st.dataframe(crit_df, use_container_width=False, hide_index=True)

            # Reasoning (RTL for Hebrew content)
            reasoning = v.get("reasoning") or ""
            if reasoning:
                st.markdown("**Reasoning:**")
                st.markdown(
                    f'<div dir="rtl" style="background:#f8f8f8;padding:10px;'
                    f'border-radius:6px;font-size:0.95em;line-height:1.6;">'
                    f"{reasoning}</div>",
                    unsafe_allow_html=True,
                )

            # Source log on demand
            case_id = v.get("case_id", "")
            filename = v.get("filename", "")
            btn_key = f"src_{case_id}_{filename}"
            if st.button("Load source log", key=btn_key):
                with st.spinner("Fetching source log…"):
                    log = data.load_source_log(case_id, filename)
                if log is None:
                    st.warning("Source log not available for this verdict.")
                else:
                    lcol1, lcol2 = st.columns(2)
                    with lcol1:
                        st.markdown("**Input:**")
                        inp = log.get("input", "")
                        if isinstance(inp, str):
                            st.markdown(
                                f'<div dir="rtl" style="background:#f0f0f0;padding:8px;'
                                f'border-radius:4px;font-size:0.9em;white-space:pre-wrap;">'
                                f"{inp}</div>",
                                unsafe_allow_html=True,
                            )
                        else:
                            st.json(inp)
                    with lcol2:
                        st.markdown("**Output:**")
                        out = log.get("output", "")
                        if isinstance(out, str):
                            st.markdown(
                                f'<div dir="rtl" style="background:#f0f0f0;padding:8px;'
                                f'border-radius:4px;font-size:0.9em;white-space:pre-wrap;">'
                                f"{out}</div>",
                                unsafe_allow_html=True,
                            )
                        else:
                            st.json(out)
