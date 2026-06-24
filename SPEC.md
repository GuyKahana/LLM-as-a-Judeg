# SPEC: Standalone LLM-as-a-Judge Service

This document is the implementation specification. Follow it as the source of truth. If anything in this document conflicts with assumptions you'd otherwise make, this document wins.

Before writing any code, produce a detailed implementation plan as markdown covering:

- File-by-file: what you will create, with a one-line purpose for each
- Order of implementation
- Any ambiguities or decisions you need confirmed
- Any assumptions you are making

Stop after the plan and wait for explicit `approved, proceed` before writing any code. If the response is anything else, treat it as feedback on the plan and revise it.

---

## Goal

Build a NEW, standalone Python repository for a daily batch service that judges prompt-turn logs produced by an existing production system. The judge:

- Reads logs READ-ONLY from a GCS bucket.
- Evaluates each turn with a hybrid rubric + golden-example approach.
- Writes verdicts to a SEPARATE GCS bucket (or a different prefix in the same bucket).
- Sends ONE daily digest alert summarizing flagged turns.

This service MUST NOT depend on, import from, or modify the production repository in any way. It treats the production repo as a black box that writes logs to GCS.

---

## Context — known facts about the production system the judge reads from

- Production writes per-turn JSON logs to `gs://{PRODUCTION_BUCKET}/logs/{case_id}/{filename}`.
- Four log JSON schemas exist:
  1. **Standard**: `{prompt: str, input: str, output: str}`
  2. **Tool-use**: `{prompt: str, input: str, output: dict}`
  3. **Boundary check**: `{input: str, output: str}` (no `prompt` field)
  4. **Duplicate check**: `{input1: object, input2: object, output: str}`
- Log filenames are stable per prompt type. Known patterns include:
  - `final_summary.json`, `findings.json`, `surgeries.json`, `sick_permits.json`, `incidents.json`, `disabilities.json`, `adl_records.json`, `accident_details.json`
  - `medical_doc_{order}.json`, `document_conditions_classifier_{order}.json`, `diagnoses_by_date_classifier_{page_num}.json`
  - `filter_diagnoses.json`, `merge_diagnoses.json`, `clean_medications.json`
  - `personal_details.json`, `past_committees.json`, `full_summary.json`, `split_document_summaries.json`
  - `Page{n}<>Page{m}.json`, `medical_doc_validator_{order}.json`, `check_duplication_{order1}<>{order2}.json`
- Langfuse may be used by production, but the judge does NOT read from Langfuse — GCS only.
- Deployment target: customer private networks with their own LLM endpoints. The judge's LLM client MUST support a configurable base URL and API key.

---

## Repository structure to create

```
llm-judge/
├── pyproject.toml
├── README.md
├── .env.example
├── .gitignore
├── Dockerfile
├── docker-compose.yml          # local dev
├── deploy/
│   └── cloud-scheduler.md      # wire Cloud Scheduler → Cloud Run job
├── src/llm_judge/
│   ├── __init__.py
│   ├── config.py               # pydantic-settings
│   ├── logging_setup.py        # structured JSON logs to stdout
│   ├── gcs_client.py           # read-only source + read/write verdict bucket
│   ├── llm_client.py           # judge LLM client honoring base URL
│   ├── log_parser.py           # parse all 4 schema variants
│   ├── rubrics/
│   │   ├── __init__.py
│   │   ├── registry.py         # filename pattern → rubric mapping
│   │   └── prompts/            # one .md per rubric family, committed
│   ├── golden_examples.py      # load from gs://{VERDICT_BUCKET}/golden/{prompt_type}/
│   ├── evaluator.py            # judge one turn → verdict dict
│   ├── runner.py               # batch orchestration
│   ├── alerts.py               # webhook + SMTP digest
│   ├── cli.py                  # entrypoint: python -m llm_judge ...
│   └── models.py               # pydantic verdict, run summary, etc.
└── tests/
    ├── fixtures/               # sample logs for all 4 schemas
    └── test_*.py
```

---

## Components — what each does

### `config.py` (pydantic-settings, all from env)

- `PRODUCTION_BUCKET` — GCS bucket to READ from (required)
- `VERDICT_BUCKET` — GCS bucket to WRITE verdicts and read golden examples from (required; can be the same bucket with a different prefix)
- `VERDICT_PREFIX` — default `judge/`
- `GOLDEN_PREFIX` — default `golden/`
- `GCP_PROJECT_ID` — optional
- `GOOGLE_APPLICATION_CREDENTIALS` — standard GCP auth
- `JUDGE_MODEL` — default `claude-sonnet-4-6`
- `JUDGE_LLM_BASE_URL` — optional; when set, passed as `base_url` to the Anthropic client
- `JUDGE_LLM_API_KEY` — required
- `JUDGE_LLM_PROVIDER` — default `anthropic`; design the client so adding `openai` later is a single-file change
- `JUDGE_SCORE_THRESHOLD` — default 3 (1–5 scale; score ≤ threshold flags)
- `JUDGE_LOOKBACK_HOURS` — default 24
- `JUDGE_MAX_TURNS_PER_RUN` — default 500
- `JUDGE_INPUT_TRUNCATE_CHARS` — default 30000 (truncate input, keep full output)
- `ALERT_WEBHOOK_URL` — optional
- `ALERT_EMAILS` — optional, comma-separated
- `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM` — required only if email alerts on
- `DRY_RUN` — default false; when true, evaluates but writes/sends nothing

### `gcs_client.py`

- One client with two roles: read-only against `PRODUCTION_BUCKET`, read/write against `VERDICT_BUCKET`.
- `list_logs_modified_since(hours: int) -> Iterator[BlobMeta]` over `logs/` prefix; returns `(case_id, filename, modified_time)`.
- `read_log(case_id, filename) -> dict`
- `verdict_exists(case_id, filename) -> bool` against `{VERDICT_PREFIX}{case_id}/{filename}`
- `write_verdict(case_id, filename, verdict: dict)`
- `read_golden_examples(prompt_type) -> list[dict]` from `{GOLDEN_PREFIX}{prompt_type}/`, returns up to 2, empty list if none.
- All paths configurable. No hardcoded bucket names.

### `log_parser.py`

- Single `parse_log(raw_json: dict, filename: str) -> ParsedTurn` that handles all 4 schemas.
- `ParsedTurn` exposes a uniform `{prompt, input, output, schema_variant}` to the evaluator.
- For boundary/duplicate variants, synthesize a sensible `prompt` field (e.g. `"[boundary check — no separate prompt logged]"`).

### `rubrics/registry.py`

- Maps filename → rubric name using a list of `(regex, rubric_name)` tuples. Cover every known pattern from the Context section.
- Unknown filenames return `None`; the runner counts them as "unmapped" and skips them — never crash.
- Each rubric is a markdown file under `rubrics/prompts/` with: role, 3–5 criteria scored 1–5, required JSON output format example.
- Build rubrics for these families: document summaries, final summary, extraction lists, classifiers, grouping/boundary, duplicate checks, personal/committee summaries.

### `golden_examples.py`

- For a given prompt type, fetch up to 2 example pairs from `gs://{VERDICT_BUCKET}/{GOLDEN_PREFIX}{prompt_type}/`.
- Each golden example is itself a JSON file with the same schema as a production log.
- Empty folder = no examples injected, judge still runs on rubric alone.

### `llm_client.py`

- Thin wrapper around `anthropic.Anthropic` (or `AsyncAnthropic` if needed). Honor `JUDGE_LLM_BASE_URL` via the `base_url` constructor arg.
- Single method `judge(system: str, user: str) -> str` returning raw text.
- Provider switch (`JUDGE_LLM_PROVIDER`) leaves a clear extension seam for OpenAI-compatible endpoints.

### `evaluator.py`

- Inputs: `ParsedTurn`, rubric content, golden examples.
- Builds the judge prompt: rubric (system) + golden examples (as "examples of good output") + the turn under review (truncated per `JUDGE_INPUT_TRUNCATE_CHARS`, output never truncated).
- Calls `llm_client.judge`.
- Parses strict JSON `{score: int 1-5, per_criterion: {<criterion>: int}, flagged: bool, reasoning: str}` defensively (strip code fences). On parse failure: retry once with a "respond ONLY with valid JSON" reinforcement; on second failure, record verdict `{parse_error: true, raw: <truncated raw>, flagged: false}` and continue.
- `flagged = score <= JUDGE_SCORE_THRESHOLD`.

### `runner.py`

- Orchestrates one run:
  1. List logs modified within `JUDGE_LOOKBACK_HOURS`.
  2. Filter out turns where `verdict_exists` is true.
  3. Cap at `JUDGE_MAX_TURNS_PER_RUN`.
  4. For each turn: try/except around the whole evaluation; one failure NEVER kills the run; record per-turn outcome in the summary.
  5. Write verdict to `gs://{VERDICT_BUCKET}/{VERDICT_PREFIX}{case_id}/{filename}` unless `DRY_RUN`.
  6. Build `RunSummary` (total, evaluated, skipped, unmapped, flagged, errors, by-prompt-type counts).
- Sequential execution. Concurrency is NOT in scope for v1.

### `alerts.py`

- If any flagged turns and not `DRY_RUN`: send ONE digest.
- Webhook: generic JSON POST to `ALERT_WEBHOOK_URL` with the full `RunSummary` plus a list of flagged items `{case_id, filename, prompt_type, score, reasoning_snippet}`.
- Email: plain SMTP, HTML body with the same digest. Only enabled when SMTP_* vars are set.
- Always log the summary to stdout regardless of alert outcome.

### `cli.py`

- `python -m llm_judge run` — full batch
- `python -m llm_judge run --case-id X` — single case
- `python -m llm_judge run --dry-run` — overrides config
- `python -m llm_judge calibrate` — runs the judge over `golden/` and reports any goldens it would flag (detects judge drift)
- `python -m llm_judge list-rubrics` — prints filename → rubric mapping

### `Dockerfile`

- Slim Python base, copy source, install via `pyproject.toml`. Entrypoint: `python -m llm_judge run`. Runs as non-root.

### `deploy/cloud-scheduler.md`

- Step-by-step: build image, push to Artifact Registry, create a Cloud Run Job, schedule via Cloud Scheduler (daily at 02:00 UTC by default).
- Include the equivalent K8s CronJob YAML as an alternative for private-network customers.

---

## Tests (pytest, mock all GCS and LLM calls)

- `test_log_parser.py` — all 4 schema variants parse correctly; malformed JSON handled.
- `test_rubric_registry.py` — every known filename pattern maps; unknown returns `None`.
- `test_evaluator.py` — judge JSON parsed; malformed JSON triggers one retry then records `parse_error`; input truncation respects limit and never truncates output.
- `test_runner.py` — already-judged turns skipped; one failing turn does not kill the run; lookback filter respected.
- `test_alerts.py` — digest fires only when flagged > 0; webhook payload shape; no email when SMTP unset.
- `test_config.py` — `JUDGE_LLM_BASE_URL` reaches the client constructor.
- `test_golden_examples.py` — empty folder returns `[]`; max 2 returned when more present.

---

## Constraints — do not violate

- This repo is fully standalone. Do NOT import anything from the production codebase. Do NOT add the production repo as a git submodule, vendored package, or dependency.
- Do NOT write to `PRODUCTION_BUCKET` under any prefix. All writes go to `VERDICT_BUCKET`.
- No hardcoded buckets, URLs, model names, or credentials. Everything via env/config.
- Never log secrets. Mask API keys in error messages.
- No new third-party deps beyond: `google-cloud-storage`, `anthropic`, `pydantic`, `pydantic-settings`, `python-dotenv`, `pytest`, `pytest-mock`. If something else is needed, stop and ask.
- LLM provider abstraction must be a clean seam — `JUDGE_LLM_BASE_URL` reaching the constructor and a one-file path to add OpenAI-compatible support later. Do NOT actually implement OpenAI in v1.
- Stop and ask before: adding any dependency outside the list above, changing the verdict JSON schema, or introducing concurrency.
- After each major component completes, output: `✅ [component name] — [one-line summary]`

---

## Done when

- `python -m llm_judge run --dry-run` executes end-to-end against a mocked GCS bucket in tests.
- All tests pass.
- `docker build .` succeeds; container runs locally with a mounted GCP service-account key against a test bucket.
- README documents: env vars (table), how to add a rubric, golden set folder format, private-network deployment notes (base URL, SMTP, K8s CronJob alternative), and how to wire Cloud Scheduler.
- No reference to the production repo anywhere in code, configs, or docs.

