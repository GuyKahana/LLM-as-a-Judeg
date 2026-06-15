# Deploying LLM Judge with Cloud Scheduler

This guide covers deploying the LLM Judge as a daily batch job on Google Cloud Platform using Cloud Run + Cloud Scheduler, with an alternative Kubernetes CronJob configuration at the end.

---

## Prerequisites

- GCP project with billing enabled
- `gcloud` CLI authenticated (`gcloud auth login`)
- Artifact Registry repository for Docker images
- Service account with:
  - `roles/storage.objectViewer` on `PRODUCTION_BUCKET`
  - `roles/storage.objectCreator` on `VERDICT_BUCKET`
  - `roles/storage.objectViewer` on `GOLDEN_BUCKET`

---

## Step 1: Enable Required APIs

```bash
gcloud services enable \
  run.googleapis.com \
  cloudscheduler.googleapis.com \
  artifactregistry.googleapis.com \
  --project=YOUR_PROJECT_ID
```

---

## Step 2: Create a Service Account

```bash
gcloud iam service-accounts create llm-judge-runner \
  --display-name="LLM Judge Runner" \
  --project=YOUR_PROJECT_ID

SA_EMAIL="llm-judge-runner@YOUR_PROJECT_ID.iam.gserviceaccount.com"

# Grant read access to the production bucket
gcloud storage buckets add-iam-policy-binding gs://YOUR_PRODUCTION_BUCKET \
  --member="serviceAccount:${SA_EMAIL}" \
  --role="roles/storage.objectViewer"

# Grant write access to the verdict bucket
gcloud storage buckets add-iam-policy-binding gs://YOUR_VERDICT_BUCKET \
  --member="serviceAccount:${SA_EMAIL}" \
  --role="roles/storage.objectAdmin"

# If GOLDEN_BUCKET is separate, also grant read access
gcloud storage buckets add-iam-policy-binding gs://YOUR_GOLDEN_BUCKET \
  --member="serviceAccount:${SA_EMAIL}" \
  --role="roles/storage.objectViewer"
```

---

## Step 3: Build and Push the Docker Image

```bash
PROJECT_ID=YOUR_PROJECT_ID
REGION=us-central1
IMAGE="$REGION-docker.pkg.dev/$PROJECT_ID/llm-judge/llm-judge:latest"

# Create Artifact Registry repo if needed
gcloud artifacts repositories create llm-judge \
  --repository-format=docker \
  --location=$REGION \
  --project=$PROJECT_ID

# Configure Docker auth
gcloud auth configure-docker "$REGION-docker.pkg.dev"

# Build and push
docker build -t "$IMAGE" .
docker push "$IMAGE"
```

---

## Step 4: Store Secrets in Secret Manager

```bash
# Store the Anthropic API key
echo -n "sk-ant-YOUR_KEY" | gcloud secrets create judge-llm-api-key \
  --data-file=- \
  --project=$PROJECT_ID

# Grant the service account access
gcloud secrets add-iam-policy-binding judge-llm-api-key \
  --member="serviceAccount:${SA_EMAIL}" \
  --role="roles/secretmanager.secretAccessor" \
  --project=$PROJECT_ID
```

---

## Step 5: Deploy to Cloud Run (Jobs)

```bash
gcloud run jobs create llm-judge \
  --image="$IMAGE" \
  --region=$REGION \
  --service-account="${SA_EMAIL}" \
  --set-secrets="JUDGE_LLM_API_KEY=judge-llm-api-key:latest" \
  --set-env-vars="\
PRODUCTION_BUCKET=YOUR_PRODUCTION_BUCKET,\
VERDICT_BUCKET=YOUR_VERDICT_BUCKET,\
JUDGE_MODEL=claude-sonnet-4-6,\
JUDGE_LLM_PROVIDER=anthropic,\
JUDGE_SCORE_THRESHOLD=3,\
JUDGE_LOOKBACK_HOURS=24,\
JUDGE_MAX_TURNS_PER_RUN=500,\
JUDGE_MAX_WORKERS=5,\
JUDGE_INPUT_TRUNCATE_CHARS=150000,\
JUDGE_PARSE_ERROR_THRESHOLD=10,\
ALERT_ON_SUCCESS=true,\
ALERT_WEBHOOK_URL=https://hooks.slack.com/services/YOUR/WEBHOOK/URL" \
  --task-timeout=3600 \
  --max-retries=1 \
  --project=$PROJECT_ID
```

---

## Step 6: Schedule with Cloud Scheduler

```bash
# Create a service account for the scheduler to invoke the Cloud Run job
gcloud iam service-accounts create llm-judge-scheduler \
  --display-name="LLM Judge Scheduler" \
  --project=$PROJECT_ID

SCHEDULER_SA="llm-judge-scheduler@YOUR_PROJECT_ID.iam.gserviceaccount.com"

# Grant the scheduler SA permission to run the Cloud Run job
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:${SCHEDULER_SA}" \
  --role="roles/run.invoker"

# Create the daily schedule (runs at 06:00 UTC every day)
gcloud scheduler jobs create http llm-judge-daily \
  --location=$REGION \
  --schedule="0 6 * * *" \
  --uri="https://${REGION}-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/${PROJECT_ID}/jobs/llm-judge:run" \
  --message-body="{}" \
  --oauth-service-account-email="${SCHEDULER_SA}" \
  --project=$PROJECT_ID
```

---

## Step 7: Verify

```bash
# Trigger a manual run to verify
gcloud run jobs execute llm-judge --region=$REGION --project=$PROJECT_ID

# Check logs
gcloud logging read "resource.type=cloud_run_job AND resource.labels.job_name=llm-judge" \
  --limit=50 \
  --project=$PROJECT_ID
```

---

## Outage Recovery

If the service was down and you need to catch up on missed evaluations:

```bash
# Re-evaluate the last 48 hours of logs
gcloud run jobs update llm-judge \
  --update-env-vars="JUDGE_LOOKBACK_HOURS=48" \
  --region=$REGION --project=$PROJECT_ID

gcloud run jobs execute llm-judge --region=$REGION --project=$PROJECT_ID

# Restore the default afterwards
gcloud run jobs update llm-judge \
  --update-env-vars="JUDGE_LOOKBACK_HOURS=24" \
  --region=$REGION --project=$PROJECT_ID
```

Or pass it via the CLI override (override without changing the job config):

```bash
# Using docker-compose locally:
docker-compose run judge python -m llm_judge run --lookback-hours 48
```

---

## Kubernetes CronJob Alternative

If you prefer running on Kubernetes (e.g. GKE), use the following manifest:

```yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: llm-judge
  namespace: default
spec:
  # Run daily at 06:00 UTC
  schedule: "0 6 * * *"
  concurrencyPolicy: Forbid
  successfulJobsHistoryLimit: 3
  failedJobsHistoryLimit: 3
  jobTemplate:
    spec:
      backoffLimit: 1
      activeDeadlineSeconds: 3600
      template:
        spec:
          restartPolicy: Never
          serviceAccountName: llm-judge-ksa  # Workload Identity SA
          containers:
            - name: llm-judge
              image: REGION-docker.pkg.dev/YOUR_PROJECT_ID/llm-judge/llm-judge:latest
              imagePullPolicy: Always
              resources:
                requests:
                  cpu: "500m"
                  memory: "512Mi"
                limits:
                  cpu: "2"
                  memory: "2Gi"
              env:
                - name: PRODUCTION_BUCKET
                  value: "YOUR_PRODUCTION_BUCKET"
                - name: VERDICT_BUCKET
                  value: "YOUR_VERDICT_BUCKET"
                - name: JUDGE_MODEL
                  value: "claude-sonnet-4-6"
                - name: JUDGE_LLM_PROVIDER
                  value: "anthropic"
                - name: JUDGE_SCORE_THRESHOLD
                  value: "3"
                - name: JUDGE_LOOKBACK_HOURS
                  value: "24"
                - name: JUDGE_MAX_TURNS_PER_RUN
                  value: "500"
                - name: JUDGE_MAX_WORKERS
                  value: "5"
                - name: JUDGE_INPUT_TRUNCATE_CHARS
                  value: "150000"
                - name: JUDGE_PARSE_ERROR_THRESHOLD
                  value: "10"
                - name: ALERT_ON_SUCCESS
                  value: "true"
                - name: ALERT_WEBHOOK_URL
                  value: "https://hooks.slack.com/services/YOUR/WEBHOOK/URL"
                - name: JUDGE_LLM_API_KEY
                  valueFrom:
                    secretKeyRef:
                      name: llm-judge-secrets
                      key: anthropic-api-key
---
# Kubernetes Secret (create with kubectl, not committed to git)
# kubectl create secret generic llm-judge-secrets \
#   --from-literal=anthropic-api-key=sk-ant-YOUR_KEY
apiVersion: v1
kind: Secret
metadata:
  name: llm-judge-secrets
  namespace: default
type: Opaque
# data: populated by kubectl create secret (base64 encoded)
```

### Workload Identity Setup (GKE)

```bash
# Create a Kubernetes Service Account
kubectl create serviceaccount llm-judge-ksa --namespace=default

# Bind to the GCP service account via Workload Identity
gcloud iam service-accounts add-iam-policy-binding "${SA_EMAIL}" \
  --role="roles/iam.workloadIdentityUser" \
  --member="serviceAccount:${PROJECT_ID}.svc.id.goog[default/llm-judge-ksa]"

kubectl annotate serviceaccount llm-judge-ksa \
  --namespace=default \
  iam.gke.io/gcp-service-account="${SA_EMAIL}"
```
