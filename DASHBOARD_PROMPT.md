# Prompt for Claude Code — Build a Streamlit dashboard for the LLM Judge

> Paste everything below this line into Claude Code, run from the repo root (`LLM-as-a-Judeg/`).
> Read the existing code before writing anything. Do not modify production logs.

---

## Context

This repo (`llm-judge/`) is a standalone batch service that evaluates prompt-turn logs from a production medical-document LLM system. A run reads logs, evaluates each turn against a rubric with Claude, writes one **verdict** JSON per turn, and produces a **run summary**. I want a local **dashboard** to browse run results and show them to my manager. It's for local development now, but design it so it can later point at a live/cloud source with minimal change.

Before coding, read these files so your implementation matches reality:
- `llm-judge/src/llm_judge/models.py` — the `Verdict` and `RunSummary` schemas (source of truth — do not invent fields).
- `llm-judge/src/llm_judge/runner.py` — how a batch run works and how the `RunSummary` is built.
- `llm-judge/src/llm_judge/cli.py` — the `run` / `calibrate` / `list-rubrics` commands.
- `llm-judge/src/llm_judge/storage/` — `StorageProvider` interface + `local.py`, `gcs.py`, `client.py`, `factory.py`. **Reuse this abstraction** so the dashboard is storage-agnostic.
- `llm-judge/src/llm_judge/config.py` and `.env.example` — settings and paths.
- `llm-judge/src/llm_judge/rubrics/registry.py` — rubric/prompt-type names.

## How data is laid out today (local dev)

- Storage root: `LOCAL_STORAGE_BASE_DIR` (default `local-data/`), provider `local`.
- **Input logs (read-only, never write here):** `local-data/prod/logs/<case_id>/<filename>.json`
- **Verdicts (output):** `local-data/verdicts/judge/<case_id>/<filename>.json` (`VERDICT_PREFIX=judge/`)
- A `case_id` looks like `16_בלכנר_פרידה_זל_20260615_101030` — note Hebrew text + a `_YYYYMMDD_HHMMSS` suffix. Filenames can contain `<>` (e.g. `Page12<>Page13.json`) and rubric-style names (e.g. `medical_doc_validator_8.json`).

### Verdict JSON fields (per turn)
`case_id, filename, prompt_type` (rubric, e.g. `classifier`, `grouping_boundary`, `final_summary`, `document_summaries`, `extraction_list`, `duplicate_check`, `personal_committee`), `schema_variant` (`standard` | `tool_use` | `boundary_check` | `duplicate_check`), `score` (int 1–5 or null), `per_criterion` (dict, keys vary by rubric), `flagged` (bool), `reasoning` (str, often long, frequently Hebrew), `parse_error` (bool), `raw_response` (str|null), `evaluated_at` (ISO-8601 UTC).

### RunSummary fields (per batch)
`run_id, started_at, finished_at, total_logs, evaluated, skipped_existing, unmapped, flagged, errors, parse_errors, by_prompt_type` (dict prompt_type→count), `flagged_items` (list of `{case_id, filename, prompt_type, score, reasoning_snippet}`).

Scores `<= JUDGE_SCORE_THRESHOLD` (default 3) are flagged.

## IMPORTANT — fix a gap first (backend change)

Right now `RunSummary` is **returned and logged/emailed but never persisted to disk**, so there is no runs history to display. Add persistence using the existing storage abstraction so it also works on GCS later:

1. In `runner.py` (or a small helper), after building the `RunSummary`, write it via the `StorageProvider` to a new prefix: `verdicts/runs/<run_id>.json` (i.e. alongside `judge/`, under the verdict bucket/root). Add a `RUNS_PREFIX` setting (default `runs/`) in `config.py` / `.env.example`. Respect `--dry-run` (don't write on dry runs, or write to a clearly marked dry-run area — pick the simplest correct behavior and note it).
2. Add a `run_id: str` field to the `Verdict` model and stamp the current run's id onto every verdict written, so verdicts can be tied back to a run. Keep it backward-compatible (default `""` / optional) so existing verdict files without it still load.
3. Keep changes minimal and covered by the existing test style; don't break the `local` and `gcs` providers.

## Build the dashboard

Create a `dashboard/` package with a **Streamlit** app (`streamlit run dashboard/app.py`). Add `streamlit` (and any charting dep you use, prefer Streamlit-native or `altair`) to an optional dependency group in `pyproject.toml` (e.g. `[project.optional-dependencies] dashboard`). Add a short "Dashboard" section to `README.md` with the launch command.

**Data access:** read through the existing `StorageProvider`/`StorageClient` (driven by the same env config), NOT by hardcoding `local-data` paths. This is what makes it repointable at GCS later. Cache reads (`st.cache_data`) and handle a case with hundreds of verdict files without lag.

### Pages / views

1. **Runs list** — table of all runs from `verdicts/runs/*.json`: short run_id, started/finished, duration, scope (case-id or lookback), and counts (total / evaluated / flagged / errors / parse_errors) plus flagged-rate %. Sortable, newest first. Click a row to open run detail. If no run files exist yet (older data), gracefully fall back to grouping verdicts by `case_id` and show a notice that summaries weren't persisted for those.

2. **Run detail** — headline metric cards (evaluated, flagged, flagged-rate, errors, parse_errors, duration); a bar chart of `by_prompt_type`; a score-distribution chart; the `flagged_items` table; and a link/expander into the verdicts for that run/case.

3. **Verdicts explorer** — filter by case_id, prompt_type, schema_variant, flagged (yes/no), score range, and a free-text search over `reasoning`. Table shows score, a colored flagged badge, prompt_type, schema_variant, evaluated_at. Expanding a row shows full `reasoning`, the `per_criterion` breakdown (small bar/table), and — read on demand from the corresponding log file under `prod/logs/<case_id>/<filename>` — the original `input`/`output` for side-by-side context. Don't crash if the source log is missing.

4. **Trigger / re-run** — a form to launch the judge: a case-id dropdown (populated from the log case directories), a dry-run checkbox, and an optional lookback-hours field. On submit, invoke the CLI as a subprocess (`python -m llm_judge run [--case-id ...] [--dry-run] [--lookback-hours N]`), stream stdout/stderr live into the UI, and refresh the runs list when it finishes. Disable the button while a run is in flight; surface non-zero exit codes clearly.

### UX details that matter
- **Hebrew / RTL:** `case_id`, `reasoning`, inputs and outputs are frequently Hebrew. Render them readably (RTL where appropriate, e.g. `dir="rtl"` for reasoning/text blocks) and ensure mixed Hebrew/Latin doesn't garble.
- Make flagged rows visually obvious (color). Show "N/A" cleanly for null scores and for `parse_error` verdicts (treat them as a distinct status, not score 0).
- Clean enough to screenshot/demo to a manager: a clear title, summary KPIs up top, sensible empty states, and no stack traces leaking to the UI.

### Constraints
- **Never write to or modify `prod/logs/`** — it is read-only input.
- Keep the dashboard self-contained under `dashboard/` and importable from the existing package; don't entangle it with `runner.py` beyond the persistence change above.
- No new heavyweight infra. One command to launch.

## Future-proofing (don't build now, just don't block it)
Because the dashboard reads through `StorageProvider`, switching from local to GCS should be config-only. Structure the data layer so a future "live monitor" (polling a running source / newer GCS verdicts) could be added as another data source without rewriting the views. Leave a brief note in the README on what changes for cloud/live use.

## Deliverables
1. The backend persistence change (RunSummary written to `runs/`, `run_id` on verdicts) + updated config/.env.example + tests.
2. The `dashboard/` Streamlit app with the four views above.
3. `pyproject.toml` optional dep group + README "Dashboard" section with launch instructions.
4. Verify end-to-end against the existing `local-data/` sample (the `16_בלכנר…` case): run the app, confirm runs list, run detail, verdicts explorer with Hebrew rendering, and a triggered dry-run all work. Report what you verified.
