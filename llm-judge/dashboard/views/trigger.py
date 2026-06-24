"""View 4 — Trigger a batch run."""

from __future__ import annotations

import os
import subprocess
import sys
import time

import streamlit as st

from dashboard import data

# Map the friendly toggle labels to the source key the data layer understands.
_SOURCES = {"Cloud (production bucket)": "cloud", "Local files": "local"}


def render() -> None:
    st.header("Trigger Batch Run")

    # The case ID to run (None ⇒ lookback over all cases).
    selected: str | None = None
    lookback: int | None = None

    # --- Where to look: configured production root (cloud) or local disk ----
    source_label = st.radio(
        "Look for logs in",
        list(_SOURCES),
        horizontal=True,
        help="Cloud reads the configured production root (GCS in your hybrid "
        "setup). Local reads test cases under "
        "LOCAL_STORAGE_BASE_DIR/PRODUCTION_BUCKET on disk.",
    )
    source = _SOURCES[source_label]
    where = "GCS" if source == "cloud" else "local disk"

    # --- Primary: type a case ID and verify it against the chosen source ----
    typed = st.text_input(
        "Case ID",
        placeholder="Enter a case ID",
        help="Type a case ID exactly as it appears under logs/, then look it "
        "up to confirm it exists before running.",
    ).strip()

    if st.button(f"Look up in {where}", disabled=not typed):
        with st.spinner(f"Looking up '{typed}' in {where}…"):
            try:
                files = data.lookup_case_files(typed, source)
                st.session_state["lookup_result"] = (typed, source, files)
                st.session_state.pop("lookup_error", None)
            except Exception as exc:
                st.session_state["lookup_result"] = (typed, source, None)
                st.session_state["lookup_error"] = str(exc)

    result = st.session_state.get("lookup_result")
    # Only honour a lookup matching the text AND source currently selected.
    if result and result[0] == typed and result[1] == source and typed:
        _, _, files = result
        if files is None:
            st.error(
                f"Lookup failed: {st.session_state.get('lookup_error', 'unknown error')}"
            )
        elif files:
            st.success(f"Found {len(files)} log file(s) for `{typed}` in {where}.")
            with st.expander("Files that will be evaluated"):
                for f in files:
                    st.write(f"• {f}")
            selected = typed  # eligible to run
        else:
            st.warning(
                f"No logs found for `{typed}` under `logs/{typed}/` in {where}. "
                "Check the spelling and the source toggle above."
            )

    # --- Alternatives: lookback window, or browse the full case list --------
    # Browsing scans every entry under the source, so it is opt-in (slow on a
    # large production bucket); typing a case ID above never triggers that scan.
    with st.expander("Other options — lookback window / browse all cases"):
        if st.checkbox("Run all cases modified in a lookback window"):
            lookback = st.number_input(
                "Lookback hours", min_value=1, max_value=720, value=24, step=1
            )
        if st.checkbox(f"Browse the full case list in {where} (slow)"):
            with st.spinner("Loading cases…"):
                cases = data.list_cases(source)
            picked = st.selectbox("Pick a case", options=[""] + cases)
            if picked:
                selected = picked

    dry_run = st.checkbox("Dry run (evaluate without writing verdicts)", value=False)

    running: bool = st.session_state.get("judge_running", False)
    # Nothing actionable until a case is resolved or we're in lookback mode.
    can_run = bool(selected) or lookback is not None

    if st.button("Run Judge", disabled=running or not can_run):
        st.session_state["judge_running"] = True
        st.session_state["run_args"] = (selected, lookback, dry_run, source)
        st.rerun()

    if running:
        selected, lookback, dry_run, source = st.session_state.get(
            "run_args", (selected, lookback, dry_run, source)
        )
        cmd = [sys.executable, "-m", "llm_judge", "run"]
        if selected:
            cmd += ["--case-id", selected]
        if dry_run:
            cmd += ["--dry-run"]
        if lookback and not selected:
            cmd += ["--lookback-hours", str(int(lookback))]

        # When the user picked Local, force the run's production root to local
        # too, so it reads the same files the lookup found (the configured root
        # may be GCS in a hybrid setup).
        run_env = os.environ.copy()
        if source == "local":
            run_env["PRODUCTION_STORAGE_PROVIDER"] = "local"

        st.info(f"Running: `{' '.join(cmd)}`  (source: {source})")

        output_lines: list[str] = []
        placeholder = st.empty()

        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                env=run_env,
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
