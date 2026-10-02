# Cloud Run backend deployment contract

> Superseded on 2026-10-02. The supported deployment is [Vercel Hobby + GitHub Actions](vercel-github-actions.md); Cloud Run is not required and no Google Cloud billing changes are authorized by this guide. The content below is a historical contract, not current setup instructions. The retained dispatcher, Dockerfile, and related dependencies are unused by the new web routes. Do not follow these rollout steps or reapply the already-live Supabase SQL.

This repository builds one container image for two Cloud Run resources. Do not
deploy until the Supabase migration has been reviewed and applied.

## Service

Use the image's default Gunicorn command. The service exposes:

- `GET /health` -> `200 {"data":{"status":"ok"}}`
- `POST /v1/scans` with a Supabase access token -> `202` and the queued scan
- `POST /v1/scans/recover-queued` with the same token -> `200`; releases only
  a queued scan older than `STALE_QUEUED_SCAN_MINUTES` (default 15)
- `409` when an active scan already exists
- `401` for a missing/expired token, `403` for a non-allowlisted account
- `503` when storage or Cloud Run job execution is unavailable

The service must accept unauthenticated network requests so Vercel can reach it;
application access is still gated by a validated Supabase bearer token and the
exact email allowlist. Restrict ingress as far as the chosen Vercel networking
setup permits.

Required environment/secrets:

- `SUPABASE_URL`
- `SUPABASE_PUBLISHABLE_KEY`
- `SUPABASE_SECRET_KEY` (preferred `sb_secret_...`; server only)
- `SUPABASE_SERVICE_ROLE_KEY` only as a temporary legacy alternative
- `ALLOWED_USER_EMAIL=dealfinder0322@gmail.com`
- `GOOGLE_CLOUD_PROJECT`
- `CLOUD_RUN_REGION`
- `CLOUD_RUN_JOB_NAME`
- `FRONTEND_ORIGIN` (the exact Vercel origin, no trailing slash)
- optional `STALE_QUEUED_SCAN_MINUTES` (5-1440, default 15)

Because the dispatcher supplies a per-execution `SCAN_RUN_ID` environment
override, grant its identity **Cloud Run Jobs Executor With Overrides**
(`roles/run.jobsExecutorWithOverrides`) on the selected job. That role contains
both `run.jobs.run` and the required `run.jobs.runWithOverrides` permission, as
documented in Google's [Cloud Run IAM roles reference](https://docs.cloud.google.com/run/docs/reference/iam/roles)
and the [`jobs.run` REST method](https://docs.cloud.google.com/run/docs/reference/rest/v2/projects.locations.jobs/run).
Do not give the frontend Google credentials or the Supabase server key.

## Job

Use the same image and override its command to:

```text
python -m deal_finder.scan_job
```

Required environment/secrets:

- `SUPABASE_URL`
- `SUPABASE_SECRET_KEY` (preferred `sb_secret_...`; server only)
- `SUPABASE_SERVICE_ROLE_KEY` only as a temporary legacy alternative
- `GEMINI_API_KEY` (secret)
- optional Gemini and scraper tuning values already supported by `config.py`

The dispatcher supplies `SCAN_RUN_ID` for each execution. Configure the job with
one task and `maxRetries=0`. Do not schedule the job. Do not set the final job
timeout until complete production scans have been measured; the application does
not enforce a 30-minute timeout.

The image sends process output to Cloud Logging and places its compatibility log
file under the writable `/tmp` filesystem. Do not treat that temporary file as
persistent storage.

## Operational gates

1. Apply the SQL migration and run Supabase security/performance advisors.
2. Create only `dealfinder0322@gmail.com` in Supabase Auth and disable public signup.
3. Deploy the job first, then grant the dispatcher identity permission to run it.
4. Deploy the service and set its allowed frontend origin.
5. Run one controlled scan and verify queued -> scanning -> evaluating -> saving -> completed.
6. Confirm the job has no retries, the service scales to zero, and no secret is in browser output.

The daily database cleanup deletes scan runs older than three days and cascades
to listings and evaluations. Targets and the Auth user are retained.

## Queued dispatch recovery

If Google accepts a launch request but no job ever claims it, an authenticated
caller can send an empty `POST /v1/scans/recover-queued` request. The response is:

```json
{"data":{"recovered":true,"scan":{"id":"<uuid>","status":"failed"}}}
```

When there is no eligible queued scan, `recovered` is `false` and `scan` is
`null`. Recovery uses an atomic `status=queued` and age filter. It never changes
`scanning`, `evaluating`, or `saving` records, so this is not a running-scan
timeout and does not introduce the deferred 30-minute limit.
