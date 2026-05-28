#!/usr/bin/env bash
# Build + deploy the eResources service to Cloud Run.
#
# Mirrors the patronchat deploy pattern. Non-secret config is read from .env
# (gitignored); the four secrets live in Secret Manager and are wired in with
# --set-secrets. Run infra/setup-gcp.sh once first.
#
#   ./deploy.sh

set -euo pipefail
cd "$(dirname "$0")"

PROJECT=${GCP_PROJECT:-your-library-esources}
REGION=${REGION:-us-central1}
SERVICE=esources
IMAGE="gcr.io/${PROJECT}/${SERVICE}:$(date -u +%Y%m%dT%H%M%SZ)"

# Load non-secret config (GOOGLE_CLIENT_ID, PUBLIC_CIDRS, etc.).
if [[ -f .env ]]; then
  set -a; source .env; set +a
fi

: "${PUBLIC_BASE_URL:?set in .env — e.g. https://your-eresources-domain.org}"
: "${GOOGLE_CLIENT_ID:?set in .env}"
: "${PUBLIC_CIDRS:?set in .env — RHPL public IP ranges, comma-separated}"

echo "→ building ${IMAGE}"
gcloud builds submit . --project="${PROJECT}" --tag="${IMAGE}"

echo "→ deploying ${SERVICE} to ${REGION}"
gcloud run deploy "${SERVICE}" \
  --project="${PROJECT}" \
  --region="${REGION}" \
  --image="${IMAGE}" \
  --service-account="esources-run@${PROJECT}.iam.gserviceaccount.com" \
  --allow-unauthenticated \
  --max-instances=5 \
  --memory=512Mi \
  --cpu=1 \
  --concurrency=80 \
  --timeout=60s \
  --set-env-vars="^|^GCP_PROJECT=${PROJECT}|PUBLIC_BASE_URL=${PUBLIC_BASE_URL}|SESSION_MINUTES=${SESSION_MINUTES:-30}|PUBLIC_CIDRS=${PUBLIC_CIDRS}|TRUSTED_PROXY_HOPS=${TRUSTED_PROXY_HOPS:-2}|GOOGLE_CLIENT_ID=${GOOGLE_CLIENT_ID}|ADMIN_EMAIL_DOMAIN=${ADMIN_EMAIL_DOMAIN:-rhpl.org}|PAPI_BASE_URL=${PAPI_BASE_URL:-https://your-polaris-server/PAPIService}|PAPI_LANG_ID=${PAPI_LANG_ID:-1033}|PAPI_APP_ID=${PAPI_APP_ID:-100}|PAPI_ORG_ID=${PAPI_ORG_ID:-3}|PAPI_API_ACCESS_ID=${PAPI_API_ACCESS_ID:-localpull}|LOGIN_RATE_MAX=${LOGIN_RATE_MAX:-5}|LOGIN_RATE_WINDOW_MIN=${LOGIN_RATE_WINDOW_MIN:-15}|ENABLE_WHOAMI=${ENABLE_WHOAMI:-0}" \
  --set-secrets="SECRET_KEY=esources-secret-key:latest,GOOGLE_CLIENT_SECRET=esources-google-client-secret:latest,FERNET_KEY=esources-fernet-key:latest,PAPI_API_SECRET=esources-papi-api-secret:latest"

echo "→ deployed. Cloud Run URL:"
gcloud run services describe "${SERVICE}" \
  --project="${PROJECT}" --region="${REGION}" --format='value(status.url)'
echo "→ patrons reach it at ${PUBLIC_BASE_URL} once Firebase Hosting is connected."
