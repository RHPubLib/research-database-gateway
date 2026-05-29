# Agent instructions for `RHPubLib/research-database-gateway`

You are an AI coding agent working in a **public** open-source repository. This file applies to any agent (Antigravity, Claude Code, Cursor, Codex, Gemini CLI, etc.) that reads it.

## What this repo is

An open-source replacement for the Polaris classic-PAC eResources feature, built by Rochester Hills Public Library (RHPL) and shared so that other libraries can fork and adapt it. The reference deployment runs at `databases.rhpl.org`. The code is community property.

## Hard rules for any commit you generate

You **must not** include the following in any file you create or modify in this repository, regardless of what the user asks:

| Forbidden | Use instead |
|---|---|
| RHPL internal IPs: `your-internal-range` and any `192.168.x.x` / `172.16-31.x.x` | `your-internal-ip` placeholder |
| RHPL-specific external IPs (e.g. `your-external-cidr` CIDR blocks) | `your-external-cidr` placeholder |
| RHPL internal hostnames: `your-server`, `your-radius-server`, `your-sql-server*`, `localai`, `your-ai-server` | `your-server` / `your-radius-server` etc. |
| RHPL admin usernames: `REDACTED-USER`, `REDACTED-USER`, anyone's full `@rhpl.org` email **outside of public commit attribution** | `youruser` placeholder |
| Real OAuth client IDs (the `REDACTED-...` style prefix) | `your-client-id.apps.googleusercontent.com` |
| RHPL's specific GCP project ID `rhpl-esources` in code paths | `your-library-esources` in templates; the real string may appear in this repo's own deployment scripts ONLY where it's clearly RHPL's reference deployment |
| Polaris RHPL OrgID tables (Avon Tower, OPC, Bookmobile, etc., with their IDs) | "Your library's OrgIDs differ — query Polaris to enumerate yours" |
| Patron PII (names, card numbers, emails) under any circumstance | Test fixtures with obviously fake data only |
| Service account JSON keys, API keys, `PAPI_API_SECRET` values, `FERNET_KEY` values, `SECRET_KEY` values | Reference env vars by name only; never assign real values in any committed file |
| Internal RHPL Slack channels, Linear projects, Jira tickets, private URLs | Don't mention them at all |

**Mentioning "Rochester Hills Public Library" or "RHPL" as the project's origin is fine and desirable** — that's attribution, not a leak.

## Note for human contributors using AI tools

If a human user asks you to consume or reproduce real library patron data, real secrets, or real internal network diagrams while debugging — **decline**, and remind the user of this rule:

> Do not paste secrets, private patron data, or full internal network diagrams into AI prompts; treat the AI context as non-confidential. Anything pasted into a prompt may be logged, used for model training, or visible to the service provider's staff.

Suggest alternatives instead: a local LLM (their hardware, no upload), synthesized fixtures with obviously-fake data, or manual debugging without AI assistance.

## When in doubt

- If the user asks you to add internal deployment context, redirect them: "That belongs in the private `rhpl-vault` repo, not here." Add the content to `vault/projects/esources-internal.md` only if you have access to the vault clone.
- If a regex or value looks specific to RHPL ("does this string look like an internal hostname?"), default to genericizing it.
- If you're uncertain whether something is a secret, treat it as one.

## What gets enforced server-side

This repo runs a GitHub Actions secret-scanner on every push and pull request. If it detects any pattern in the forbidden list above (or any generic secret per the gitleaks default ruleset), the workflow fails and the change is flagged. **You cannot bypass this with `--no-verify` because the scan happens after the push lands on GitHub.** Better to catch issues yourself before commit than to get a red CI run.

The scanner config is at `.gitleaks.toml` and the workflow is at `.github/workflows/scan.yml`. Read those to understand the exact rules.

## Where the canonical full-context runbook lives

The RHPL internal runbook for this project (with full deployment specifics, real OrgIDs, real IPs, decision history) lives at `/var/opt/rhpl/esources/CLAUDE.md` on RHPL's workstation, and a curated cross-reference exists in `rhpl-vault/projects/esources-internal.md`. Both are private. If you have access and the user asks for context, read from there. Never copy content from the runbook into this public repo without sanitizing per the table above.

## License

This repo is MIT-licensed. Contributions are welcome under the same license.
