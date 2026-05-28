#!/usr/bin/env bash
# One-time Google Cloud setup for the eResources service. Idempotent — safe
# to re-run. Assumes the GCP project already exists and billing is linked
# (billing account configured in advance).
#
#   PROJECT=your-library-esources ./infra/setup-gcp.sh
#
# Everything provisioned here stays within the GCP free tier.

set -euo pipefail

PROJECT=${PROJECT:-your-library-esources}
REGION=${REGION:-us-central1}
SA_NAME=esources-run
SA_EMAIL="${SA_NAME}@${PROJECT}.iam.gserviceaccount.com"

echo "→ project: ${PROJECT}   region: ${REGION}"

echo "→ enabling APIs"
gcloud services enable \
  run.googleapis.com \
  firestore.googleapis.com \
  secretmanager.googleapis.com \
  cloudbuild.googleapis.com \
  artifactregistry.googleapis.com \
  --project="${PROJECT}"

echo "→ creating Firestore (Native mode) in ${REGION}"
gcloud firestore databases create --location="${REGION}" \
  --type=firestore-native --project="${PROJECT}" 2>/dev/null \
  || echo "   (Firestore database already exists — skipping)"

echo "→ creating runtime service account ${SA_EMAIL}"
gcloud iam service-accounts describe "${SA_EMAIL}" --project="${PROJECT}" >/dev/null 2>&1 \
  || gcloud iam service-accounts create "${SA_NAME}" \
       --project="${PROJECT}" \
       --display-name="eResources Cloud Run runtime"

echo "→ granting roles/datastore.user (Firestore read/write)"
gcloud projects add-iam-policy-binding "${PROJECT}" \
  --member="serviceAccount:${SA_EMAIL}" \
  --role="roles/datastore.user" --condition=None >/dev/null

echo "→ granting roles/secretmanager.secretAccessor (read the 4 secrets)"
gcloud projects add-iam-policy-binding "${PROJECT}" \
  --member="serviceAccount:${SA_EMAIL}" \
  --role="roles/secretmanager.secretAccessor" --condition=None >/dev/null

echo "→ enabling Firestore TTL on login_attempts.expire_at (auto-purge counters)"
gcloud firestore fields ttls update expire_at \
  --collection-group=login_attempts --project="${PROJECT}" 2>/dev/null \
  || echo "   (TTL policy already set, or will apply once the collection exists)"

cat <<NEXT

──────────────────────────────────────────────────────────────────────────────
Infrastructure ready. Remaining one-time steps (see README.md for detail):

1. Create the four secrets in Secret Manager (values are NOT stored in git):

   printf '%s' "\$(python3 -c 'import secrets;print(secrets.token_urlsafe(48))')" \\
     | gcloud secrets create esources-secret-key --data-file=- --project=${PROJECT}

   printf '%s' "\$(python3 -c 'from cryptography.fernet import Fernet;print(Fernet.generate_key().decode())')" \\
     | gcloud secrets create esources-fernet-key --data-file=- --project=${PROJECT}

   printf '%s' 'PASTE_GOOGLE_OAUTH_CLIENT_SECRET' \\
     | gcloud secrets create esources-google-client-secret --data-file=- --project=${PROJECT}

   printf '%s' 'PASTE_PAPI_API_SECRET' \\
     | gcloud secrets create esources-papi-api-secret --data-file=- --project=${PROJECT}

   NOTE: esources-fernet-key must match the FERNET_KEY used by the migration
   importer, or previously-saved vendor passwords cannot be decrypted.

2. Create an OAuth 2.0 Client (Web application) in the GCP console:
   APIs & Services → Credentials. Authorized redirect URI:
       https://your-eresources-domain.org/admin/callback
   Put the client ID in .env (GOOGLE_CLIENT_ID); the client secret into the
   esources-google-client-secret secret above.

3. Set a budget alert (Billing → Budgets) at ~\$5/year as a guardrail.

4. Deploy:  ./deploy.sh

5. Connect Firebase Hosting for your-eresources-domain.org:
       firebase projects:addfirebase ${PROJECT}
       firebase deploy --only hosting,firestore:rules --project ${PROJECT}
   then add the custom domain your-eresources-domain.org in the Firebase console.
──────────────────────────────────────────────────────────────────────────────
NEXT
