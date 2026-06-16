"""LLM Judge Dashboard — main Streamlit entry point.

Launch with:
    streamlit run dashboard/app.py
from the llm-judge/ directory.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure the project root (llm-judge/) is on sys.path so both `dashboard`
# and `llm_judge` (under src/) are importable regardless of how Streamlit
# was invoked.
_project_root = Path(__file__).parent.parent  # llm-judge/
_src_dir = _project_root / "src"
for _p in [str(_project_root), str(_src_dir)]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

import streamlit as st

st.set_page_config(
    page_title="LLM Judge Dashboard",
    layout="wide",
    page_icon="⚖️",
)

# ---------------------------------------------------------------------------
# Config validation — fail fast with a helpful message
# ---------------------------------------------------------------------------
try:
    from llm_judge.config import Settings

    _settings = Settings()  # type: ignore[call-arg]
except Exception as cfg_err:
    st.error(
        "**Configuration error** — could not load Settings.\n\n"
        f"```\n{cfg_err}\n```\n\n"
        "Make sure a `.env` file exists in the working directory with at least:\n"
        "```\n"
        "STORAGE_PROVIDER=local\n"
        "PRODUCTION_BUCKET=prod\n"
        "VERDICT_BUCKET=verdicts\n"
        "JUDGE_LLM_API_KEY=<your-key>\n"
        "```\n"
        "See `.env.example` for a full reference."
    )
    st.stop()

# ---------------------------------------------------------------------------
# Sidebar navigation
# ---------------------------------------------------------------------------
VIEWS = ["Runs", "Run Detail", "Verdicts Explorer", "Trigger"]

if "current_view" not in st.session_state:
    st.session_state["current_view"] = "Runs"

with st.sidebar:
    st.title("⚖️ LLM Judge")
    st.divider()
    chosen = st.radio(
        "Navigate",
        options=VIEWS,
        index=VIEWS.index(st.session_state["current_view"]),
        label_visibility="collapsed",
    )
    if chosen != st.session_state["current_view"]:
        st.session_state["current_view"] = chosen
        st.rerun()

    st.divider()
    if st.button("Refresh data"):
        st.cache_data.clear()
        st.rerun()

# ---------------------------------------------------------------------------
# Render active view
# ---------------------------------------------------------------------------
view = st.session_state["current_view"]

if view == "Runs":
    from dashboard.views.runs_list import render
    render()
elif view == "Run Detail":
    from dashboard.views.run_detail import render
    render()
elif view == "Verdicts Explorer":
    from dashboard.views.verdicts_explorer import render
    render()
elif view == "Trigger":
    from dashboard.views.trigger import render
    render()
