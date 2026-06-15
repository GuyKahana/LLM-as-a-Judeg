# LLM Judge

A standalone daily batch service that evaluates prompt-turn logs produced by a production LLM system. The judge reads logs READ-ONLY from a GCS bucket, evaluates each turn with a hybrid rubric + golden-example approach using Claude, writes verdicts to a separate GCS bucket, and sends a daily digest alert summarising flagged turns.

This service is **completely independent** — it does not import from or modify any production repository.

---

## Quick Start

```bash
pip install -e ".[dev]"
cp .env.example .env
# Fill in your real values in .env

python -m llm_judge run
```

---

## Environment Variable Reference

| Variable | Type | Default | Required | Description |
|---|---|---|---|---|
| `PRODUCTION_BUCKET` | string | — | **Yes** | GCS bucket containing production logs (READ ONLY) |
| `VERDICT_BUCKET` | string | — | **Yes** | GCS bucket where verdicts are written |
| `GOLDEN_BUCKET` | string | `VERDICT_BUCKET` | No | GCS bucket for golden examples; defaults to `VERDICT_BUCKET` |
| `VERDICT_PREFIX` | string | `judge/` | No | Prefix inside `VERDICT_BUCKET` for verdict files |
| `GOLDEN_PREFIX` | string | `golden/` | No | Prefix inside `GOLDEN_BUCKET` for golden example files |
| `GCP_PROJECT_ID` | string | — | No | GCP project ID for GCS operations |
| `GOOGLE_APPLICATION_CREDENTIALS` | string | — | No | Path to GCP service account key file (standard ADC) |
| `JUDGE_LLM_PROVIDER` | string | `anthropic` | No | LLM provider. Only `anthropic` is supported. |
| `JUDGE_LLM_API_KEY` | string | — | **Yes** | Anthropic API key |
| `JUDGE_MODEL` | string | `claude-sonnet-4-6` | No | Claude model ID |
| `JUDGE_LLM_BASE_URL` | string | — | No | Override Anthropic API base URL (for private network proxy) |
| `JUDGE_SCORE_THRESHOLD` | int | `3` | No | Scores ≤ this value trigger flagging |
| `JUDGE_LOOKBACK_HOURS` | int | `24` | No | Hours of log history to scan in a standard run |
| `JUDGE_MAX_TURNS_PER_RUN` | int | `500` | No | Maximum turns evaluated per run (safety cap) |
| `JUDGE_MAX_WORKERS` | int | `5` | No | Thread pool workers for parallel evaluation |
| `JUDGE_INPUT_TRUNCATE_CHARS` | int | `150000` | No | Max characters per input before truncation |
| `JUDGE_PARSE_ERROR_THRESHOLD` | int | `10` | No | Force-send alert if parse errors exceed this |
| `ALERT_WEBHOOK_URL` | string | — | No | Webhook URL for digest alerts (e.g. Slack) |
| `ALERT_EMAILS` | string | — | No | Comma-separated email recipients for digest |
| `ALERT_ON_SUCCESS` | bool | `true` | No | When `false`, skip sending if no flags and no errors above threshold |
| `SMTP_HOST` | string | — | No | SMTP server hostname (required for email alerts) |
| `SMTP_PORT` | int | `587` | No | SMTP port |
| `SMTP_USER` | string | — | No | SMTP username |
| `SMTP_PASSWORD` | string | — | No | SMTP password |
| `SMTP_FROM` | string | — | No | From address for digest emails |
| `DRY_RUN` | bool | `false` | No | Evaluate without writing verdicts or sending alerts |

---

## CLI Reference

```
python -m llm_judge --help

Commands:
  run           Run a batch evaluation job
  calibrate     Run judge over all golden examples and report drift
  list-rubrics  Print all filename pattern -> rubric name mappings
```

### `run`

```bash
python -m llm_judge run [OPTIONS]

Options:
  --case-id TEXT         Evaluate all logs for a specific case ID.
                         Ignores --lookback-hours entirely — all logs for the
                         case are evaluated regardless of age.
  --dry-run              Evaluate without writing verdicts or sending alerts.
  --lookback-hours INT   Override JUDGE_LOOKBACK_HOURS for this run.
                         Ignored when --case-id is set.
```

### `calibrate`

Runs the judge over all golden examples and flags any that score ≤ `JUDGE_SCORE_THRESHOLD` as potential judge drift. Goldens are always positive examples (expected to score well); low scores indicate the judge may be miscalibrated.

```bash
python -m llm_judge calibrate
```

### `list-rubrics`

Prints all filename pattern → rubric name mappings.

```bash
python -m llm_judge list-rubrics
```

---

## How to Add a Rubric

1. Create a new Markdown file in `src/llm_judge/rubrics/prompts/<rubric_name>.md`.

2. The file must include:
   - A system role description
   - 3–5 named evaluation criteria with 1–5 scoring guidance
   - A `## Required Output Format` section with the exact JSON schema

3. Register the filename patterns in `src/llm_judge/rubrics/registry.py` by adding entries to `RUBRIC_PATTERNS`:

   ```python
   (re.compile(r"^my_new_log\.json$"), "my_rubric"),
   ```

4. Add test cases to `tests/test_rubric_registry.py`.

---

## Golden Set Folder Format

Golden examples are stored in GCS at:

```
{GOLDEN_BUCKET}/{GOLDEN_PREFIX}{rubric_name}/
```

For example, if `GOLDEN_BUCKET=my-bucket`, `GOLDEN_PREFIX=golden/`, and the rubric is `final_summary`:

```
gs://my-bucket/golden/final_summary/example1.json
gs://my-bucket/golden/final_summary/example2.json
```

Each golden JSON file must:
- Be a valid log file matching the rubric's expected schema
- Contain `"expected_verdict": "pass"` to indicate it is a positive (high-quality) example

Up to 2 goldens per rubric are loaded. These are passed to the judge as calibration examples in the system prompt. Empty folders are silently ignored.

---

## Scale Limitations (v1)

The current implementation performs a **full GCS prefix scan** (`logs/`) on every run to find recently modified blobs. This approach is simple and correct but does not scale beyond approximately **10,000–50,000 blobs** in the `PRODUCTION_BUCKET/logs/` prefix before list latency becomes significant.

**Mitigation**: For large deployments, consider:
- Using a date-partitioned prefix structure (e.g. `logs/2024/01/15/{case_id}/`) and scanning only the current day's prefix.
- Maintaining an external index (e.g. a Firestore or BigQuery table of new blobs) and querying that instead of full GCS scans.
- Enabling GCS Pub/Sub notifications to build a queue-based architecture.

Document this limitation when onboarding new team members.

---

## Outage Recovery

If the service was offline and you need to catch up on missed evaluations, run with an extended lookback:

```bash
python -m llm_judge run --lookback-hours 48
```

> **Note**: The `--lookback-hours` flag is **ignored** when `--case-id` is set. Use `--lookback-hours` for time-based catch-up runs after an outage; use `--case-id` to reprocess a specific case.

---

## `--case-id` Behaviour

When `--case-id` is provided, the runner calls `list_all_logs_for_case(case_id)` instead of the time-filtered list. **All logs for that case are evaluated regardless of their age** — the `JUDGE_LOOKBACK_HOURS` setting and the `--lookback-hours` flag are both ignored entirely. This is useful for:

- Reprocessing a specific case after rubric changes
- Debugging a single case
- Evaluating historical cases not covered by the lookback window

```bash
python -m llm_judge run --case-id case-12345
```

---

## Private-Network Deployment

### Custom Anthropic API Base URL

If your infrastructure routes Anthropic API calls through a private proxy:

```
JUDGE_LLM_BASE_URL=https://my-anthropic-proxy.internal/v1
```

The Anthropic client will use this base URL instead of the default `https://api.anthropic.com`.

### SMTP Configuration

For email digests through an internal SMTP relay:

```
SMTP_HOST=smtp.internal.example.com
SMTP_PORT=587
SMTP_USER=llm-judge@internal.example.com
SMTP_PASSWORD=...
SMTP_FROM=llm-judge@internal.example.com
ALERT_EMAILS=oncall@example.com,lead@example.com
```

---

## Cloud Scheduler Deployment

See [`deploy/cloud-scheduler.md`](deploy/cloud-scheduler.md) for step-by-step instructions including:

- Building and pushing the Docker image to Artifact Registry
- Deploying to Cloud Run Jobs
- Scheduling with Cloud Scheduler (daily at 06:00 UTC)
- Kubernetes CronJob YAML alternative

---

## Running Locally with docker-compose

```bash
cp .env.example .env
# Fill in real values

# Build and run
docker-compose up --build

# One-off dry run
docker-compose run judge python -m llm_judge run --dry-run

# Catch-up run (extended lookback)
docker-compose run judge python -m llm_judge run --lookback-hours 48

# Evaluate a specific case
docker-compose run judge python -m llm_judge run --case-id case-12345
```

---

## Running Tests

```bash
pip install -e ".[dev]"
pytest tests/ -v
```

---

## Project Structure

```
llm-judge/
├── pyproject.toml
├── README.md
├── .env.example
├── .gitignore
├── Dockerfile
├── docker-compose.yml
├── deploy/
│   └── cloud-scheduler.md
├── src/llm_judge/
│   ├── __init__.py
│   ├── __main__.py
│   ├── config.py          # pydantic-settings config
│   ├── logging_setup.py   # structured JSON logging
│   ├── gcs_client.py      # GCS I/O (READ from PRODUCTION_BUCKET, WRITE to VERDICT_BUCKET)
│   ├── llm_client.py      # Anthropic SDK wrapper
│   ├── log_parser.py      # schema detection and normalisation
│   ├── rubrics/
│   │   ├── registry.py    # filename → rubric name mapping
│   │   └── prompts/       # one .md per rubric family
│   ├── golden_examples.py # golden example loading
│   ├── evaluator.py       # single-turn evaluation logic
│   ├── runner.py          # batch orchestration
│   ├── alerts.py          # digest sending (webhook + email)
│   ├── cli.py             # Click CLI
│   └── models.py          # Pydantic models
└── tests/
    ├── fixtures/
    ├── conftest.py
    ├── test_log_parser.py
    ├── test_rubric_registry.py
    ├── test_evaluator.py
    ├── test_runner.py
    ├── test_alerts.py
    ├── test_config.py
    └── test_golden_examples.py
```
