# LLM Judge

A standalone daily batch service that evaluates prompt-turn logs produced by a production LLM system. The judge reads logs READ-ONLY from a GCS bucket, evaluates each turn with a hybrid rubric + golden-example approach using Claude, writes verdicts to a separate GCS bucket, and sends a daily digest alert summarising flagged turns.

This service is **completely independent** — it does not import from or modify any production repository.

---

## Dashboard

A Streamlit dashboard lets you browse runs, explore verdicts, and trigger new batch evaluations from a browser.

### Install

```bash
pip install -e ".[dashboard]"
```

### Launch

```bash
# From the llm-judge/ directory:
streamlit run dashboard/app.py
```

The dashboard reads from the same `.env` configuration as the batch runner — no extra setup needed.

**Cloud / GCS note:** to point at a GCS bucket instead of local files, set the following in `.env` — no code changes required:

```
STORAGE_PROVIDER=gcs
PRODUCTION_BUCKET=my-prod-logs-bucket
VERDICT_BUCKET=my-verdict-bucket
```

---

## Quick Start — First-Time Setup

### 1. Create a virtual environment

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

### 2. Configure environment variables

```bash
cp .env.example .env
```

Open `.env` and fill in at minimum:

```
PRODUCTION_BUCKET=your-production-logs-bucket
VERDICT_BUCKET=your-verdict-output-bucket
JUDGE_LLM_API_KEY=sk-ant-...
```

All other variables have sensible defaults (see [Environment Variable Reference](#environment-variable-reference)).

### 3. Authenticate with GCP

```bash
gcloud auth application-default login
# or point to a service account key:
export GOOGLE_APPLICATION_CREDENTIALS=/path/to/key.json
```

### 4. Verify with a dry run (no writes, no alerts)

Run against real GCS without writing any verdict files or sending any alerts:

```bash
python -m llm_judge run --dry-run
```

This is the recommended first step against a real bucket. You will see a full run summary in stdout but nothing will be written to `VERDICT_BUCKET`.

### 5. Run for real

```bash
python -m llm_judge run
```

---

## Testing Without GCS — Local Storage

Set `STORAGE_PROVIDER=local` to run the full service against your local filesystem instead of GCS. No GCP credentials needed.

```bash
# In .env or as shell exports:
STORAGE_PROVIDER=local
# LOCAL_STORAGE_BASE_DIR defaults to local-data/ inside the project root

# Minimal required vars still needed:
PRODUCTION_BUCKET=prod         # becomes local-data/prod/
VERDICT_BUCKET=verdicts        # becomes local-data/verdicts/
JUDGE_LLM_API_KEY=sk-ant-...
```

The local provider mirrors the GCS path structure under `LOCAL_STORAGE_BASE_DIR` (default `local-data/`, already gitignored). To seed it with test logs:

```bash
mkdir -p local-data/prod/logs/case-001
cp tests/fixtures/standard_log.json \
   local-data/prod/logs/case-001/final_summary.json

python -m llm_judge run --dry-run
```

---

## Environment Variable Reference

| Variable | Type | Default | Required | Description |
|---|---|---|---|---|
| **Storage** | | | | |
| `STORAGE_PROVIDER` | string | `gcs` | No | Storage backend: `gcs`, `local`, `s3` (stub), `azure` (stub) |
| `LOCAL_STORAGE_BASE_DIR` | string | `local-data` | No | Root directory for `STORAGE_PROVIDER=local`; resolved relative to CWD; bucket names become subdirectories; `local-data/` is gitignored |
| `PRODUCTION_BUCKET` | string | — | **Yes** | GCS bucket (or local subdirectory) containing production logs — READ ONLY |
| `VERDICT_BUCKET` | string | — | **Yes** | GCS bucket (or local subdirectory) where verdicts are written |
| `GOLDEN_BUCKET` | string | `VERDICT_BUCKET` | No | Bucket for golden examples; defaults to `VERDICT_BUCKET` |
| `VERDICT_PREFIX` | string | `judge/` | No | Path prefix inside `VERDICT_BUCKET` for verdict files |
| `GOLDEN_PREFIX` | string | `golden/` | No | Path prefix inside `GOLDEN_BUCKET` for golden example files |
| **GCP** | | | | |
| `GCP_PROJECT_ID` | string | — | No | GCP project ID (optional; inferred from ADC when not set) |
| `GOOGLE_APPLICATION_CREDENTIALS` | string | — | No | Path to GCP service account key file (standard ADC) |
| **LLM** | | | | |
| `JUDGE_LLM_PROVIDER` | string | `anthropic` | No | LLM provider — only `anthropic` is implemented; others raise `NotImplementedError` |
| `JUDGE_LLM_API_KEY` | string | — | **Yes** | Anthropic API key |
| `JUDGE_MODEL` | string | `claude-sonnet-4-6` | No | Claude model ID to use for judging |
| `JUDGE_LLM_BASE_URL` | string | — | No | Override Anthropic API base URL (private network proxy; see [Private-Network Deployment](#private-network-deployment)) |
| **Judging behaviour** | | | | |
| `JUDGE_SCORE_THRESHOLD` | int | `3` | No | Scores ≤ this value flag a turn (1–5 scale) |
| `JUDGE_LOOKBACK_HOURS` | int | `24` | No | Hours of log history to scan per standard run |
| `JUDGE_MAX_TURNS_PER_RUN` | int | `500` | No | Hard cap on turns evaluated per run |
| `JUDGE_MAX_WORKERS` | int | `5` | No | Thread-pool workers for parallel turn evaluation |
| `JUDGE_INPUT_TRUNCATE_CHARS` | int | `150000` | No | Max characters of turn input before truncation (duplicate-check inputs each get half) |
| `JUDGE_PARSE_ERROR_THRESHOLD` | int | `10` | No | Force-send alert when parse errors in a run exceed this, even if `ALERT_ON_SUCCESS=false` |
| **Alerting** | | | | |
| `ALERT_WEBHOOK_URL` | string | — | No | Webhook endpoint for digest POST (e.g. Slack incoming webhook) |
| `ALERT_EMAILS` | string | — | No | Comma-separated email recipients for digest |
| `ALERT_ON_SUCCESS` | bool | `true` | No | When `false`, skip sending digest if there are no flags and parse errors ≤ threshold |
| **SMTP** (required only when `ALERT_EMAILS` is set) | | | | |
| `SMTP_HOST` | string | — | No | SMTP server hostname |
| `SMTP_PORT` | int | `587` | No | SMTP port |
| `SMTP_USER` | string | — | No | SMTP authentication username |
| `SMTP_PASSWORD` | string | — | No | SMTP authentication password |
| `SMTP_FROM` | string | — | No | From address for digest emails |
| **Other** | | | | |
| `DRY_RUN` | bool | `false` | No | Evaluate turns but skip writing verdicts and sending alerts (also available as `--dry-run` CLI flag) |

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

### Custom LLM Base URL

If your infrastructure routes Anthropic API calls through a private proxy or an Anthropic-compatible on-prem endpoint:

```
JUDGE_LLM_BASE_URL=https://my-anthropic-proxy.internal/v1
JUDGE_LLM_API_KEY=<key-for-your-proxy>
```

The Anthropic client passes `base_url` directly to its constructor, so any proxy that speaks the Anthropic Messages API will work.

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

### Kubernetes CronJob

For customers running in a private network without Cloud Run, the equivalent K8s manifest:

```yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: llm-judge
  namespace: llm-judge
spec:
  schedule: "0 2 * * *"       # 02:00 UTC daily
  concurrencyPolicy: Forbid
  jobTemplate:
    spec:
      template:
        spec:
          restartPolicy: Never
          containers:
            - name: judge
              image: YOUR_REGISTRY/llm-judge:latest
              envFrom:
                - secretRef:
                    name: llm-judge-secrets   # holds all env vars from .env.example
              volumeMounts:
                - name: gcp-key
                  mountPath: /gcp-key
                  readOnly: true
              env:
                - name: GOOGLE_APPLICATION_CREDENTIALS
                  value: /gcp-key/key.json
          volumes:
            - name: gcp-key
              secret:
                secretName: gcp-service-account-key
```

Create the secrets:

```bash
kubectl create namespace llm-judge
kubectl create secret generic llm-judge-secrets \
  --from-env-file=.env \
  -n llm-judge
kubectl create secret generic gcp-service-account-key \
  --from-file=key.json=/path/to/sa-key.json \
  -n llm-judge
```

See [`deploy/cloud-scheduler.md`](deploy/cloud-scheduler.md) for the full Cloud Run + Cloud Scheduler alternative.

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
│   ├── config.py          # pydantic-settings — all env vars
│   ├── logging_setup.py   # structured JSON logging to stdout
│   ├── storage/
│   │   ├── base.py        # StorageProvider ABC (list_files/read_file/write_file/file_exists)
│   │   ├── gcs.py         # Google Cloud Storage implementation
│   │   ├── local.py       # Local filesystem implementation (dev / tests)
│   │   ├── s3.py          # AWS S3 stub (raises NotImplementedError)
│   │   ├── azure.py       # Azure Blob Storage stub (raises NotImplementedError)
│   │   ├── factory.py     # create_provider(root, config) — dispatches on STORAGE_PROVIDER
│   │   └── client.py      # StorageClient — domain operations on top of StorageProvider
│   ├── llm_client.py      # Anthropic SDK wrapper
│   ├── log_parser.py      # schema detection and normalisation (4 variants)
│   ├── rubrics/
│   │   ├── registry.py    # filename → rubric name mapping
│   │   └── prompts/       # one .md per rubric family
│   ├── golden_examples.py # golden example loading
│   ├── evaluator.py       # single-turn evaluation logic
│   ├── runner.py          # batch orchestration (ThreadPoolExecutor)
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
