"""View 5 — Upload a new case with log files."""

from __future__ import annotations

import re
import subprocess
import sys
import time

import streamlit as st

from dashboard import data


def _valid_case_id(name: str) -> bool:
    return bool(re.match(r"^[A-Za-z0-9_\-\.א-ת ]+$", name)) and len(name.strip()) > 0


def render() -> None:
    st.header("Upload New Case")

    st.markdown(
        "Create a new case folder and upload log files to it. "
        "After uploading you can trigger the judge directly from this page."
    )

    # -----------------------------------------------------------------------
    # Step 1 — name the case
    # -----------------------------------------------------------------------
    st.subheader("1. Case ID")
    case_id = st.text_input(
        "Case ID",
        placeholder="e.g. my-case-001",
        help="Used as the folder name under logs/. Letters, digits, hyphens, underscores and spaces are allowed.",
    )

    # -----------------------------------------------------------------------
    # Step 2 — upload files
    # -----------------------------------------------------------------------
    st.subheader("2. Upload log files")
    uploaded = st.file_uploader(
        "Select JSON log files",
        type=["json"],
        accept_multiple_files=True,
        help="Upload one or more .json log files for this case.",
    )

    # -----------------------------------------------------------------------
    # Step 3 — create the case
    # -----------------------------------------------------------------------
    st.subheader("3. Create case")

    can_create = bool(case_id and _valid_case_id(case_id) and uploaded)
    create_clicked = st.button("Create case & upload files", disabled=not can_create)

    if not case_id:
        st.caption("Enter a Case ID above to continue.")
    elif not _valid_case_id(case_id):
        st.warning("Case ID contains invalid characters.")
    elif not uploaded:
        st.caption("Upload at least one .json file to continue.")

    if create_clicked and can_create:
        files = [(f.name, f.read()) for f in uploaded]
        try:
            written = data.upload_case_logs(case_id.strip(), files)
            st.success(
                f"Case **{case_id.strip()}** created with {len(written)} file(s):\n"
                + "\n".join(f"- `{n}`" for n in written)
            )
            st.session_state["upload_case_id"] = case_id.strip()
        except Exception as exc:
            st.error(f"Upload failed: {exc}")
            return

    # -----------------------------------------------------------------------
    # Step 4 — optionally trigger the judge on this case
    # -----------------------------------------------------------------------
    ready_case = st.session_state.get("upload_case_id")
    if ready_case:
        st.divider()
        st.subheader("4. Run judge on this case")
        st.info(f"Ready to evaluate case **{ready_case}**.")

        dry_run = st.checkbox("Dry run (evaluate without writing verdicts)", value=False, key="upload_dry_run")
        running: bool = st.session_state.get("upload_judge_running", False)

        if st.button("Run Judge", disabled=running, key="upload_run_btn"):
            st.session_state["upload_judge_running"] = True
            st.rerun()

        if running:
            cmd = [sys.executable, "-m", "llm_judge", "run", "--case-id", ready_case]
            if dry_run:
                cmd += ["--dry-run"]

            st.info(f"Running: `{' '.join(cmd)}`  (source: local)")
            output_lines: list[str] = []
            placeholder = st.empty()

            try:
                # Uploaded cases live on the local filesystem, so the run must
                # be fully local too — otherwise it would read from the
                # configured (possibly cloud) production root and find nothing.
                proc = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,
                    env=data.local_run_env(),
                )

                while True:
                    line = proc.stdout.readline() if proc.stdout else ""
                    if line:
                        output_lines.append(line.rstrip())
                        placeholder.code("\n".join(output_lines[-100:]), language=None)
                    elif proc.poll() is not None:
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
                    st.cache_data.clear()
                else:
                    st.error(f"Run finished with exit code {exit_code}.")

            except Exception as exc:
                st.error(f"Failed to launch runner: {exc}")
            finally:
                st.session_state["upload_judge_running"] = False
