# RHPL eResources service

Replaces the Polaris classic-PAC eSource feature. Patrons reach research
databases at `https://your-eresources-domain.org`; in-building IPs go straight
through, off-site patrons verify a library card. Staff manage the catalog in a
Google-OAuth admin UI. Runs on Cloud Run + Firestore + Firebase Hosting — GCP
free tier.

## Cost

Expected **$0/month** (matches `patronchat`). Cloud Run scale-to-zero,
Firestore (~200 docs), Secret Manager, Firebase Hosting, Cloud Build, and
Cloud Logging all sit inside their free tiers. Set a ~$5/year budget alert as
a guardrail. Avoid Cloud SQL (~$8–10/mo) and an external Load Balancer
(~$18/mo) — this design uses neither.

## First-time setup

Prereqs: a GCP project `your-library-esources` with billing linked; `gcloud` and
`firebase` CLIs; project-owner access.

1. **Provision GCP infrastructure**
   ```
   PROJECT=your-library-esources ./infra/setup-gcp.sh
   ```
   Enables APIs, creates the Firestore database, the `esources-run` service
   account, IAM bindings, and the login-counter TTL policy. It prints the
   remaining manual steps — do them:

2. **Create the four Secret Manager secrets** (commands printed by the script):
   `esources-secret-key`, `esources-fernet-key`,
   `esources-google-client-secret`, `esources-papi-api-secret`.
   Keep a copy of the Fernet key — the migration importer needs the same one.

3. **Create the OAuth client** — GCP console → APIs & Services → Credentials →
   OAuth 2.0 Client (Web). Authorized redirect URI:
   `https://your-eresources-domain.org/admin/callback`.

4. **Create `.env`** from `.env.example`. For deployment only the non-secret
   values are needed: `PUBLIC_BASE_URL`, `GOOGLE_CLIENT_ID`,
   `PUBLIC_CIDRS` (RHPL's public IP ranges), `TRUSTED_PROXY_HOPS`, etc.
   The four secrets come from Secret Manager, not `.env`.

5. **Budget alert** — Billing → Budgets → ~$5/year.

## Deploy

```
./deploy.sh
```
Builds the container (Cloud Build), deploys to Cloud Run, prints the service
URL. Then connect the custom domain:
```
firebase projects:addfirebase your-library-esources
firebase deploy --only hosting,firestore:rules --project your-library-esources
```
and add `your-eresources-domain.org` as a custom domain in the Firebase console
(create the DNS record it asks for).

## One-time data migration from Polaris

Run against the Polaris `Polaris` SQL Server database (read-only):

1. `migrate/01_discover_attributes.sql` — reveals the real DWI attribute names
   (the URL attribute, description, and the "EM" tag). Note them.
2. Edit `migrate/02_extract_esources.sql` with those names, run it, and save
   its two result sets as UTF-8 CSVs:
   `migrate/extract/esources.csv` and `migrate/extract/categories.csv`.
3. Preview, then import:
   ```
   .venv/bin/python migrate/import_extract.py --dry-run        # parse + report
   export GCP_PROJECT=your-library-esources FERNET_KEY=<same key as the secret>
   gcloud auth application-default login
   .venv/bin/python migrate/import_extract.py                  # writes Firestore
   ```
   It upserts by `legacy_entry_id` (safe to re-run). Reconcile the count
   against query 4 of step 1.
4. In the admin UI, review the `on_campus_only` flag on each record (all
   imported as off).

## Cutover

- Repoint the Wix "Research Databases" menu item to `https://your-eresources-domain.org/`.
- Old `.../esources.aspx?Target=NNN` links are handled by `/esources?Target=NNN`.
- After ~30–60 days of confirmed traffic, retire the Polaris eSource segment.
  Keep the DWI tables read-only as an archive; keep a backup of the CSVs.

## Verify

```
.venv/bin/python -m pytest -q                 # 32 unit tests
```
End-to-end (see the plan's verification section for the full list):

- **IP detection** — set `ENABLE_WHOAMI=1`, hit `/whoami` from a library
  workstation (expect `on_campus: true`) and off-site (`false`). If wrong,
  adjust `TRUSTED_PROXY_HOPS` and redeploy. Disable `/whoami` afterwards.
- **PAPI** — off-site, a good card+PIN signs in; a bad barcode and a bad PIN
  both give the same generic error.
- **Session expiry** — set `SESSION_MINUTES=1`, confirm re-prompt after a minute.
- **In-library-only** — off-site, a flagged resource shows the in-library page.
- **Credentials** — a resource with a vendor login shows the interstitial.
- **Admin** — `@rhpl.org` can CRUD; other domains are rejected.
- **Bookmark** — `/esources?Target=<legacy id>` redirects to `/go/<slug>`.

## Local development

```
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt pytest
.venv/bin/python -m pytest -q
```
Running the full app locally needs a `.env` and Firestore access
(`gcloud auth application-default login`); then `.venv/bin/python app.py`
serves on `http://127.0.0.1:8080`.

## Operations

- **Logs** — Cloud Logging (Cloud Run console). Login successes/failures and
  admin changes are logged; barcodes/PINs and vendor passwords never are.
- **Add/edit databases** — the admin UI at `/admin`.
- **Rotate a secret** — add a new Secret Manager version, redeploy. Rotating
  `esources-secret-key` logs out all sessions. Do **not** rotate
  `esources-fernet-key` without re-encrypting stored vendor passwords.
- **Login lockout** — 5 attempts / 15 min per IP and per barcode
  (`LOGIN_RATE_MAX`, `LOGIN_RATE_WINDOW_MIN`); a successful login clears it.
