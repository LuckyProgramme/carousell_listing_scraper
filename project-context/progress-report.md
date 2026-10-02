# Deal Finder hosted rebuild progress report

> Historical 2026-09-30 report. Cloud Run was superseded by the approved Vercel/GitHub Actions architecture on 2026-10-02. See [current context](context.md) and [deployment guide](../docs/vercel-github-actions.md) for current progress; do not use this report as rollout instructions.

Updated: 2026-09-30 (Asia/Manila)
Coordinator: root Codex agent
Status: local build, live Supabase schema, owner authentication, and target import verified; hosting rollout pending

## Objective

Replace the Google Sheets-based workflow with a private single-user web application:

- Vercel hosts a Next.js frontend.
- Supabase is the only persistent data store.
- Cloud Run hosts an authenticated dispatcher and a separate Python scan job.
- Gemini continues to audit likely matches.
- The sole user is `dealfinder0322@gmail.com` through Supabase email/password authentication.

## Approved product decisions

- Scans run only when the user presses **Scan Now**.
- No scheduled scans and no automatic scan retries.
- Only one scan may be queued or running at a time.
- Targets are editable in the frontend and apply to the next scan.
- A running scan retains the target snapshot it started with.
- Supabase replaces Google Sheets completely.
- Only current targets are migrated; previous listings, deals, and Sheet history are discarded.
- Raw listings, evaluations, deals, scan status, errors, and scan history expire after three days.
- Targets and the Auth account are not removed by retention cleanup.
- The selected frontend is **Compact List** with Carousell thumbnail URLs and accessible image fallbacks.
- Thumbnails are not copied into Supabase Storage.
- No 30-minute application timeout is implemented. The Cloud Run timeout will be selected after a measured end-to-end scan.
- The Supabase-backed CLI remains temporarily, then is removed after the hosted flow is verified.
- Google Cloud billing already exists, but Codex must not create, link, change, or purchase anything billing-related without asking the user first.
- The Gemini API key must not be pasted into chat. The user will enter it directly into protected Google Cloud secret configuration before a live scan.

## Completed design and planning

- Frontend design prompt: [`design.md`](design.md)
- Approved hosted architecture: [`../docs/plans/2026-09-30-deal-finder-hosted-design.md`](../docs/plans/2026-09-30-deal-finder-hosted-design.md)
- Implementation and rollout plan: [`../docs/plans/2026-09-30-deal-finder-implementation.md`](../docs/plans/2026-09-30-deal-finder-implementation.md)
- `context.md` and `channel.md` were refreshed by Lily with the approved target architecture and `BUILD-001` ownership.

## Completed frontend work

- Added a root Next.js 16 App Router application with TypeScript and ESLint.
- Added Supabase SSR browser/server clients and session-refresh proxy.
- Added private email/password login with no signup interface.
- Added Compact List navigation: Dashboard, Targets, Results, and Sign out.
- Added target creation, editing, enable/disable, validation, and confirmed deletion.
- Added the Scan Now Vercel route, which forwards the authenticated Supabase access token to Cloud Run `POST /v1/scans`.
- Added scan progress polling for queued, scanning, evaluating, saving, completed, and failed states.
- Added duplicate-scan UI prevention and safe retry messaging.
- Added an owner-facing **Release if stuck** action backed by the protected stale-queue recovery endpoint.
- Added deal and all-listing views for only the newest completed scan, with Carousell thumbnail URLs, image fallbacks, prices, savings, match facts, and source links.
- Kept the newest overall scan separate for current progress and errors, so an active or failed scan does not replace the last completed results.
- Added a server-side sole-user gate that signs out any authenticated account other than `dealfinder0322@gmail.com`.
- Added responsive desktop, tablet, and mobile styling without a second image-storage system.
- Added local public Supabase URL/publishable-key configuration in ignored `.env.local`; the Cloud Run endpoint remains unset.

Frontend verification completed:

- `npm run typecheck` passed.
- `npm run lint` passed without warnings after excluding generated Python/test caches.
- `npm run build` passed; Next.js produced the login, dashboard, scan API, recovery API, denied-account, and sign-out routes.
- Local visual QA of `/login` passed at a narrow/mobile-sized viewport.
- Browser console QA reported no warnings or errors.
- No password was entered and no live scan was started.

## Completed Python/backend work

- Added canonical typed Target, ScanRun, Listing, and Evaluation records.
- Added a provider-neutral repository boundary.
- Added a server-only Supabase REST adapter supporting modern `SUPABASE_SECRET_KEY` and legacy service-role fallback.
- Refactored the CLI to use Supabase and the reusable scan orchestration.
- Added the Cloud Run job entry point and lifecycle stages.
- Added the authenticated Flask dispatcher with `GET /health` and `POST /v1/scans`.
- Added exact email allowlisting, Supabase token verification, CORS restriction, safe errors, and Cloud Run Job launching.
- Added protected stale-queue recovery at `POST /v1/scans/recover-queued`; it only fails queued scans older than the configured threshold and never imposes a timeout on running scans.
- Made target deletion during a scan safe by storing an immutable target snapshot while leaving the optional evaluation target relationship null.
- Added immutable `target_snapshot_id` uniqueness so one listing can be evaluated against multiple snapshotted targets without permitting duplicate decisions.
- Prevented a duplicate worker that loses the queued-scan claim from overwriting the legitimate running scan's status.
- Added actual Carousell thumbnail extraction from structured data and HTML fallback.
- Added a shared service/job Dockerfile and packaged Gemini prompt.
- Added focused tests for models, dispatcher, scan orchestration, and Supabase repository behavior.

Backend verification completed:

- `31 passed` in pytest. A cache-write warning occurred on Windows but did not affect tests.
- Python compilation passed.
- Python source distribution and wheel build passed.
- The built wheel includes `prompts/audit_v1.txt`.
- `git diff --check` passed.

## Applied Supabase migration

Migration: [`../supabase/migrations/20260930000000_hosted_deal_finder.sql`](../supabase/migrations/20260930000000_hosted_deal_finder.sql)

The user applied the migration directly in Supabase. Read-only MCP inspection verified:

- empty `targets`, `scan_runs`, `listings`, and `evaluations` tables
- RLS enabled on all four tables with owner-scoped policies and the intended authenticated grants
- active-scan protection, multi-target evaluation uniqueness, and owner/scan/listing integrity constraints
- an active daily `pg_cron` cleanup that deletes scan runs older than three days and cascades their listings/evaluations
- no Supabase security-advisor findings

Because the SQL was run manually, Supabase's migration-history list is empty even though the schema is present. The performance advisor reported three informational suggestions for composite foreign-key indexes; unused-index notices are expected while every table is empty.

## Completed Auth and target cutover

- Verified the sole Auth user `dealfinder0322@gmail.com` exists and its email is confirmed.
- Visually verified **Allow new users to sign up** and **Allow anonymous sign-ins** are off, while the Email provider remains enabled.
- Imported only the current populated Price List target: `legion 5`, Hardware, `computers-tech`, Item Name search, bundle checks enabled, and a PHP 60,000 deal ceiling.
- Verified live row counts after import: one target and zero scan runs, listings, or evaluations.

## Not yet completed

- Final independent reinspection passed with no blocking findings.
- Supabase Data API access has not yet been exercised through the Deal Finder frontend; grants, RLS, user confirmation, and signup settings are verified, but the application login path remains pending deployment/local sign-in.
- Docker is not installed locally, so the image has not been built locally.
- Google Cloud CLI is not installed locally.
- No Google Cloud project/API/service identity, Cloud Run service, Cloud Run Job, secret, or billing setting has been changed by Codex.
- No Gemini key has been received, read, or configured.
- Vercel MCP is not connected in this session, so no Vercel project has been linked or deployed.
- No live Carousell/Gemini integration scan has been run through the new system.
- The final Cloud Run task timeout has not been chosen.
- Google Sheets modules remain in the repository for compatibility/reference, but the new CLI path uses Supabase.

## Current rollout gates

1. Optionally add the three advisor-suggested composite foreign-key indexes as a recorded follow-up migration.
2. Verify signed-in Data API access through the Deal Finder frontend.
3. Connect Vercel MCP and prepare the frontend deployment.
4. Prepare Google Cloud resources. Stop and ask the user immediately before any action that could alter billing or create billable usage.
5. The user enters the Gemini key directly into protected Google Cloud secret configuration.
6. Deploy the dispatcher and job, configure Vercel, and run one controlled production scan.
7. Measure scan duration/resource use, then choose the Cloud Run timeout.
8. Verify the three-day cleanup and retire the temporary CLI after the web flow is proven.

## Resume instructions

Read, in order:

1. `AGENTS.md`
2. `project-context/context.md`
3. `project-context/channel.md`
4. this progress report
5. `docs/plans/2026-09-30-deal-finder-hosted-design.md`
6. `docs/plans/2026-09-30-deal-finder-implementation.md`

Before continuing, inspect `git status --short`, do not read local secret values, and do not touch Google Cloud billing without explicit user approval.
