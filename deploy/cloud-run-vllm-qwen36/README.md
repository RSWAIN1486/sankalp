# Qwen3.6 vLLM on Cloud Run GPU

This deployment builds an OpenAI-compatible vLLM endpoint for
`Qwen/Qwen3.6-27B-FP8` on Cloud Run with one NVIDIA RTX PRO 6000 Blackwell GPU.

The Docker image bakes the Hugging Face model snapshot into `/models/qwen3.6-27b-fp8`.
That makes cold starts read model files from the container image instead of downloading
from Hugging Face at runtime. Cloud Run can still scale to zero; when it does, the
next request must start a new instance and load the model into GPU memory again.

## Defaults

- Region: `asia-southeast1`
- GPU: `nvidia-rtx-pro-6000`
- CPU/memory: `20` CPU and `80Gi`, the Cloud Run minimum for this GPU
- Served model name: `Qwen/Qwen3.6-27B-FP8`
- Initial context: `65536` tokens
- Max instances: `1`
- Concurrency: `2`
- vLLM API auth: `VLLM_API_KEY` secret

If the first revision runs out of memory, redeploy with `MAX_MODEL_LEN=32768`.
After it is stable, try `MAX_MODEL_LEN=131072` and `KV_CACHE_DTYPE=fp8`.

## One-time setup

```sh
export PROJECT_ID=yantraivisionos
export REGION=asia-southeast1
export REPOSITORY=sankalp-vllm
export SERVICE=sankalp-qwen36
export IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPOSITORY}/qwen36-vllm:latest"

gcloud config set project "${PROJECT_ID}"
gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com secretmanager.googleapis.com

gcloud artifacts repositories create "${REPOSITORY}" \
  --repository-format=docker \
  --location="${REGION}" \
  --description="Sankalp vLLM model images"

openssl rand -hex 32 | gcloud secrets create sankalp-vllm-api-key --data-file=-
```

If the Artifact Registry repository or secret already exists, keep going and reuse it.

## Build the model image

Run from the repo root:

```sh
gcloud builds submit deploy/cloud-run-vllm-qwen36 \
  --config deploy/cloud-run-vllm-qwen36/cloudbuild.yaml \
  --substitutions "_REGION=${REGION},_REPOSITORY=${REPOSITORY},_IMAGE_NAME=qwen36-vllm,_TAG=latest"
```

The build downloads the model into the image, so the first build is large and slow.
After Docker reports `Successfully built`, the push step can still sit for tens of minutes while
Artifact Registry uploads and finalizes the large model layer. That is expected for this baked-model
image. Check status with `gcloud builds list --project "${PROJECT_ID}" --limit=3` before cancelling.

If the build fails with `/bin/sh: 1: python: not found`, make sure your checkout has the current
Dockerfile. The vLLM image exposes `python3`, and this scaffold intentionally uses `python3 -m pip`
for the Hugging Face snapshot step.

### If Cloud Build cannot read the uploaded source

If `gcloud builds submit` fails with an error like:

```text
PROJECT_NUMBER-compute@developer.gserviceaccount.com does not have storage.objects.get access
```

your project is using the Compute Engine default service account as the Cloud Build runner, and
that service account does not yet have access to the default Cloud Build staging bucket. Grant the
runner the build/source-read and Artifact Registry push permissions, then retry the same build:

```sh
export PROJECT_NUMBER="$(gcloud projects describe "${PROJECT_ID}" --format='value(projectNumber)')"
export CLOUD_BUILD_SA="${PROJECT_NUMBER}-compute@developer.gserviceaccount.com"

gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
  --member="serviceAccount:${CLOUD_BUILD_SA}" \
  --role="roles/cloudbuild.builds.builder"

gcloud storage buckets add-iam-policy-binding "gs://${PROJECT_ID}_cloudbuild" \
  --member="serviceAccount:${CLOUD_BUILD_SA}" \
  --role="roles/storage.objectViewer"

gcloud artifacts repositories add-iam-policy-binding "${REPOSITORY}" \
  --location="${REGION}" \
  --member="serviceAccount:${CLOUD_BUILD_SA}" \
  --role="roles/artifactregistry.writer"
```

Wait a minute for IAM propagation before retrying.

## Deploy cold-start mode

This is the cheaper personal-use mode. The model is persisted in the image, but Cloud Run can
scale to zero and reload the model on the next request.

```sh
gcloud beta run deploy "${SERVICE}" \
  --image "${IMAGE}" \
  --region "${REGION}" \
  --gpu 1 \
  --gpu-type nvidia-rtx-pro-6000 \
  --cpu 20 \
  --memory 80Gi \
  --no-cpu-throttling \
  --cpu-boost \
  --no-gpu-zonal-redundancy \
  --min-instances 0 \
  --max-instances 1 \
  --concurrency 2 \
  --timeout 900 \
  --port 8000 \
  --startup-probe tcpSocket.port=8000,periodSeconds=1,timeoutSeconds=1,failureThreshold=1800 \
  --set-env-vars "MAX_MODEL_LEN=65536,GPU_MEMORY_UTILIZATION=0.86,MAX_NUM_SEQS=2,MAX_NUM_BATCHED_TOKENS=8192,KV_CACHE_DTYPE=auto" \
  --set-secrets "VLLM_API_KEY=sankalp-vllm-api-key:latest" \
  --allow-unauthenticated
```

### If deploy fails on `MemAllocPerProjectRegion`

The RTX PRO 6000 Cloud Run shape requires `80Gi` container memory. Some projects start with only
`40Gi` of Cloud Run memory allocation quota in a region, which causes an error like:

```text
MemAllocPerProjectRegion requested: 85899345920 allowed: 42949672960
```

Request a Cloud Run quota increase in the deploy region before retrying:

- Metric: `run.googleapis.com/mem_allocation` / `Total memory allocation`
- Region: the value of `${REGION}` (for example `asia-southeast1`)
- Minimum requested value: `80 GiB`
- Recommended requested value: `160 GiB` so one revision can be replaced cleanly later

Because this deployment uses `--no-gpu-zonal-redundancy`, also confirm or request:

- Metric: `run.googleapis.com/nvidia_rtx_pro_6000_gpu_allocation_no_zonal_redundancy`
- Region: the value of `${REGION}`
- Requested value: `1`

CPU quota must be at least `20` vCPU in the same region.

The service is public at the Cloud Run URL, but vLLM requires `Authorization: Bearer <VLLM_API_KEY>`.
For a stricter setup, put the service behind IAM and add a small authenticated proxy.

## Warm mode for active Sankalp sessions

Use this when you are about to run long agent/computer-use sessions and want the first inference
request to avoid a cold start:

```sh
gcloud run services update "${SERVICE}" \
  --region "${REGION}" \
  --min-instances 1
```

Return to cheaper mode when finished:

```sh
gcloud run services update "${SERVICE}" \
  --region "${REGION}" \
  --min-instances 0
```

Minimum instances are charged at the full GPU instance rate while warm.

## Test

```sh
export SERVICE_URL="$(gcloud run services describe "${SERVICE}" --region "${REGION}" --format='value(status.url)')"
export VLLM_API_KEY="$(gcloud secrets versions access latest --secret=sankalp-vllm-api-key)"

curl -sS "${SERVICE_URL}/v1/models" \
  -H "Authorization: Bearer ${VLLM_API_KEY}"

curl -sS "${SERVICE_URL}/v1/chat/completions" \
  -H "Authorization: Bearer ${VLLM_API_KEY}" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "Qwen/Qwen3.6-27B-FP8",
    "messages": [{"role": "user", "content": "Reply with exactly: hello"}],
    "max_tokens": 16,
    "temperature": 0
  }'
```

## Sankalp settings

In Settings -> Provider:

- Provider: `OpenAI-compatible`
- Base URL: `<SERVICE_URL>/v1`
- Model: `Qwen/Qwen3.6-27B-FP8`
- API key: the value from `gcloud secrets versions access latest --secret=sankalp-vllm-api-key`

For local computer-use tasks, Sankalp still observes and controls your Mac locally. Only the model
planner/inference request goes to Cloud Run.
