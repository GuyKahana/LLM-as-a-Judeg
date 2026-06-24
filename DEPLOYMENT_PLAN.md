# LLM Judge — Deployment Plan

**Target:** Google Cloud Platform (Cloud Run Jobs + Cloud Scheduler + GCS)  
**Timeline:** 3 weeks  
**Owner:** Guy Kahana  
**Status:** Code complete — infrastructure setup and validation remaining

---

## What is already done

| Component | Status |
|---|---|
| Core service (`src/llm_judge/`) | ✅ Complete |
| Docker container (`Dockerfile`) | ✅ Complete |
| All 4 log schema variants supported | ✅ Complete |
| 7 rubric families with scoring prompts | ✅ Complete |
| Local + GCS + S3 + Azure storage backends | ✅ Complete |
| Streamlit dashboard | ✅ Complete |
| Dry-run mode (safe testing against real buckets) | ✅ Complete |
| Alert digest (webhook + SMTP) | ✅ Complete |
| Cloud Run + Cloud Scheduler deployment guide | ✅ Written (`deploy/cloud-scheduler.md`) |
| Test suite | ✅ Complete |

---

## What still needs to happen

1. GCP infrastructure provisioned (buckets, service account, IAM roles)
2. Docker image built and pushed to Artifact Registry
3. Secrets stored in Secret Manager
4. Cloud Run Job deployed and test-run executed
5. Cloud Scheduler wired up for daily runs
6. Alert channel configured (Slack webhook or email)
7. Golden examples uploaded for rubric calibration
8. First real run validated against production logs

---

## Week-by-week timeline

### Week 1 — Infrastructure & First Run (Days 1–5)

**Goal:** The service runs successfully against real production logs, in dry-run mode, on a real GCP project.

| Day | Task | Owner | Notes |
|---|---|---|---|
| 1 | Create GCP project (or use existing), enable APIs: Cloud Run, Cloud Scheduler, Artifact Registry, Secret Manager | DevOps / Guy | One `gcloud services enable` command — see `deploy/cloud-scheduler.md` Step 1 |
| 1 | Create GCS verdict bucket (production bucket already exists) | DevOps | Read-only on production, read/write on verdict |
| 2 | Create `llm-judge-runner` service account, assign IAM roles to both buckets | DevOps | Step 2 in deployment guide |
| 2 | Store Anthropic API key in Secret Manager | Guy | `gcloud secrets create judge-llm-api-key` |
| 3 | Build Docker image, push to Artifact Registry | Guy | Step 3 in deployment guide |
| 3 | Deploy Cloud Run Job with all env vars | Guy | Step 5 in deployment guide |
| 4 | Trigger a manual **dry run** against production logs | Guy | Validates auth, bucket access, parsing, scoring — no writes |
| 4 | Review dry-run output: check parse errors, unmapped filenames, score distribution | Guy | Adjust `JUDGE_SCORE_THRESHOLD` if needed |
| 5 | Run for real (first live verdicts written to verdict bucket) | Guy | `gcloud run jobs execute llm-judge` |
| 5 | Verify verdicts appear in GCS at `gs://VERDICT_BUCKET/judge/` | Guy | Spot-check 5–10 verdict JSON files |

**End of Week 1 milestone:** Verdicts are being written to GCS. The service works.

---

### Week 2 — Automation & Alerting (Days 6–10)

**Goal:** The service runs daily without manual triggering, and sends an alert digest.

| Day | Task | Owner | Notes |
|---|---|---|---|
| 6 | Set up Slack webhook (or SMTP config) | Guy | Add `ALERT_WEBHOOK_URL` to Cloud Run job env vars |
| 6 | Trigger a test run and verify alert digest is received | Guy | Check flagged items in the digest |
| 7 | Create `llm-judge-scheduler` service account, grant `roles/run.invoker` | DevOps | Step 6 in deployment guide |
| 7 | Create Cloud Scheduler job — daily at 06:00 UTC | Guy | `gcloud scheduler jobs create http llm-judge-daily` |
| 8 | Upload 1–2 golden examples per rubric to GCS | Guy | `gs://VERDICT_BUCKET/golden/{rubric_name}/example.json` — improves scoring quality |
| 8 | Run with golden examples, compare verdict quality | Guy | Check if scores are more consistent |
| 9 | Launch Streamlit dashboard locally, confirm it reads live verdicts | Guy | `streamlit run dashboard/app.py` |
| 10 | Buffer / catch-up day for anything from Week 1 | — | — |

**End of Week 2 milestone:** Daily automation is running. Alerts are arriving. Dashboard works.

---

### Week 3 — Validation & Handover (Days 11–15)

**Goal:** Confidence in scoring quality. Boss-ready demo and handover document.

| Day | Task | Owner | Notes |
|---|---|---|---|
| 11 | Let 2–3 automated daily runs accumulate. Review flagged verdicts | Guy | Are the flagged cases actually problematic? |
| 12 | Calibrate rubrics if needed — adjust scoring criteria in `rubrics/prompts/*.md` and re-run | Guy | No code changes, only prompt edits |
| 12 | Adjust `JUDGE_SCORE_THRESHOLD` based on real data (default is 3 on a 1–5 scale) | Guy | — |
| 13 | Deploy Streamlit dashboard to Cloud Run (optional) or confirm access for boss | Guy | Can run locally for demo if Cloud Run deploy is out of scope |
| 14 | Document operational runbook: how to re-run for a specific case, how to change lookback, how to handle outages | Guy | Can reuse `deploy/cloud-scheduler.md` as base |
| 15 | Boss demo: show the dashboard, explain a flagged verdict end-to-end | Guy | — |

**End of Week 3 milestone:** Service validated. Boss demo delivered.

---

## Key configuration decisions to make before Week 1

| Decision | Current default | Recommendation |
|---|---|---|
| `JUDGE_SCORE_THRESHOLD` | 3 (scores ≤ 3 are flagged) | Start at 3, tune after seeing real score distribution |
| `JUDGE_LOOKBACK_HOURS` | 24 | Keep at 24 for daily runs |
| `JUDGE_MAX_TURNS_PER_RUN` | 500 | Raise if production generates more than 500 logs/day |
| `JUDGE_MAX_WORKERS` | 5 | Raise to 10 if runs are slow (watch Anthropic rate limits) |
| Alert channel | Not configured | Slack webhook is fastest to set up |
| GCS region | Not set | Match production bucket region to avoid egress costs |

---

## Risks & mitigations

| Risk | Mitigation |
|---|---|
| Production logs use an unknown schema variant → `unmapped` count high | Run `--dry-run` first; check runner logs for `No rubric for filename` warnings |
| LLM parse errors → `parse_error` verdicts | The evaluator retries once automatically; monitor `parse_errors` in RunSummary |
| Anthropic rate limits → slow runs | Reduce `JUDGE_MAX_WORKERS`; run at off-peak hours via Cloud Scheduler |
| Golden examples not available → weaker scoring | Not a blocker for Week 1; add them in Week 2 to improve quality |
| Cost overrun (API calls) | Dry-run first, then set `JUDGE_MAX_TURNS_PER_RUN=50` for initial live runs |

---

## Who needs to be involved

| Person | What they need to do |
|---|---|
| Guy (you) | Everything above |
| DevOps / GCP admin | Create service accounts, assign IAM roles (if you don't have project-level IAM access) |
| Boss | Approve GCP spend, sign off on score threshold, review dashboard in Week 3 demo |

---

## Cost estimate (rough)

| Item | Estimate |
|---|---|
| Cloud Run Job (1 run/day, ~10 min runtime) | < $5/month |
| Cloud Scheduler | < $1/month |
| Anthropic API (500 turns/day × Claude Sonnet) | ~$15–40/month depending on log sizes |
| GCS storage (verdicts) | < $2/month |
| **Total** | **~$20–50/month** |

---

*Plan written: 2026-06-16. Deployment guide: `deploy/cloud-scheduler.md`.*
