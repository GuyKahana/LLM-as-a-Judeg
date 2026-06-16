"""View 4 — Trigger a batch run."""

from __future__ import annotations

import subprocess
import sys
import time

import streamlit as st

from dashboard import data


def render() -> None:
    st.header("Trigger Batch Run")

    with st.spinner("Loading cases…"):
        cases = data.list_cases()

    case_options = ["All cases (lookback)"] + cases
    selected = st.selectbox("Case ID", options=case_options)

    lookback: int | None = None
    if selected == "All cases (lookback)":
        lookback = st.number_input(
            "Lookback hours", min_value=1, max_value=720, value=24, step=1
        )

    dry_run = st.checkbox("Dry run (evaluate without writing verdicts)", value=False)

    running: bool = st.session_state.get("judge_running", False)

    if st.button("Run Judge", disabled=running):
        st.session_state["judge_running"] = True
        st.rerun()

    if running:
        cmd = [sys.executable, "-m", "llm_judge", "run"]
        if selected != "All cases (lookback)":
            cmd += ["--case-id", selected]
        if dry_run:
            cmd += ["--dry-run"]
        if lookback and selected == "All cases (lookback)":
            cmd += ["--lookback-hours", str(int(lookback))]

        st.info(f"Running: `{' '.join(cmd)}`")

        output_lines: list[str] = []
        placeholder = st.empty()

        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )

            while True:
                line = proc.stdout.readline() if proc.stdout else ""
                if line:
                    output_lines.append(line.rstrip())
                    placeholder.code("\n".join(output_lines[-100:]), language=None)
                elif proc.poll() is not None:
                    # Drain any remaining output
                    remaining = proc.stdout.read() if proc.stdout else ""
                    if remaining:
                        for l in remaining.splitlines():
                            output_lines.append(l)
                    break
                else:
                    time.sleep(0.1)

            exit_code = proc.returncode
            placeholder.code("\n".join(output_lines), language=None)

            if exit_code == 0:
                st.success(f"Run completed successfully (exit code {exit_code}).")
                # Refresh cached data so the new run appears
                st.cache_data.clear()
            else:
                st.error(f"Run finished with exit code {exit_code}.")

        except Exception as exc:
            st.error(f"Failed to launch runner: {exc}")
        finally:
            st.session_state["judge_running"] = False
