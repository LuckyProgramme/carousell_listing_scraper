# Deal Finder: Vercel Hobby and GitHub Actions design

Date: 2026-10-02 (Asia/Manila)
Status: conversational architecture approved; written specification awaiting review.
Supersedes: the Cloud Run execution and dispatcher decisions in the 2026-09-30 hosted design. Other approved product decisions continue to apply.

## Purpose and success criteria

Provide a private, personal Deal Finder website where the sole user manages targets, presses Scan Now, follows progress, and sees listings and deals from the newest completed scan. Avoid the Google Cloud billing requirement by hosting the Next.js application on Vercel Hobby and running the Python scanner in GitHub Actions. Supabase remains the only application persistence layer.

The user confirmed personal, non-commercial use and approved this architecture. Success means one dashboard click launches one scan, the runner saves progress and results, and the dashboard displays the completed result without the user opening GitHub. Google Cloud services are unnecessary for this flow. Free allowances are finite; exhausted allowances may stop service. Gemini usage remains subject to the user's existing API account and quota, independently of hosting.

## Existing implementation and change boundary

- The local Next.js frontend, Supabase schema/Auth/target cutover, Python repository, scan orchestration, and scan entry point already exist. Recorded local verification passed 31 Python tests and frontend checks; this specification does not claim fresh test results.
- `app/api/scan/route.ts` and `app/api/scan/recover/route.ts` currently forward an access token to the Cloud Run dispatcher. These routes will become the server-side dispatch and recovery boundary.
- `src/deal_finder/scan_job.py` already executes a queued scan identified by `SCAN_RUN_ID`. It will become provider-neutral and run unchanged orchestration on a GitHub runner.
- The existing scan claim, target snapshots, acceptance validation, newest-completed result selection, and retention rules remain authoritative.
- No database schema change is required for this switch. The manually applied migration and empty remote migration history are a separate existing rollout concern; do not reapply the SQL.
- Cloud Run deployment files and launcher code will be retired from the supported path in the implementation plan. Existing work must be preserved and reviewed before any removal.

## Responsibilities and request flow

Vercel hosts the private interface and two short server routes. It validates identity, creates a queued scan, and calls GitHub's dispatch API. It never executes the Python scraper or waits for the full scan.

GitHub Actions checks out the configured deployment branch, prepares Python, runs the scan entry point, and exits. Runner storage is temporary. Supabase stores targets, scan lifecycle, listings, and evaluations; the browser continues reading those records through its publishable client and owner RLS.

1. The signed-in user sends a same-origin POST to `/api/scan`.
2. The route validates the cookie-backed user with Supabase Auth `getUser()`, checks the exact allowed email, and derives `owner_id` from that validated user. A cookie session or user-supplied owner ID alone is insufficient.
3. The route validates required server configuration before creating any row. A server-only Supabase client inserts a queued `scan_runs` row. The partial unique index enforces one active scan per owner, including simultaneous clicks.
4. The route calls the fixed GitHub repository/workflow/ref with input `scan_run_id`. These identifiers come from server configuration, never from browser input.
5. The route returns HTTP 202 with the existing `data.scan` object. The browser reloads/polls Supabase for progress.
6. The runner validates the input UUID, fetches the queued scan, verifies its owner is the configured sole-user UUID, and executes `run_repository_scan`. It snapshots enabled targets when it claims the scan; edits while queued apply when the scan starts, while edits after claiming affect the next scan.
7. The atomic queued claim moves the scan to scanning. Existing orchestration proceeds through evaluating, saving, and completed, or records a safe failed state.
8. Dashboard status follows the newest overall scan. Dashboard deals and Results continue showing only the newest completed scan, including while a newer scan is running or has failed.

## Server boundary and configuration

Use small server-only modules for identity validation, scan persistence operations, and GitHub dispatch. Keep outbound fetches and clocks injectable for meaningful offline tests. Privileged modules must use `server-only` and must never be imported by client components.

Vercel configuration:

- `NEXT_PUBLIC_SUPABASE_URL` and `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY`: existing public browser configuration.
- `ALLOWED_USER_EMAIL`: `dealfinder0322@gmail.com`.
- `SUPABASE_SECRET_KEY`: server-only Supabase secret for creating and recovering scans. This corrects the earlier conversational secret list, which omitted this Vercel requirement.
- `GITHUB_ACTIONS_TOKEN`: expiring fine-grained token scoped to the selected repository, with Actions write permission. The permission covers more than dispatch, so protect it as a privileged credential.
- `GITHUB_REPOSITORY`: configured owner/repository; use the existing remote after verifying access and visibility.
- `GITHUB_WORKFLOW_FILE`: `scan.yml`.
- `GITHUB_WORKFLOW_REF`: explicitly configured deployment branch; inspect the repository before choosing its value.
- `STALE_QUEUED_SCAN_MINUTES`: 15 by default, retaining existing recovery semantics.

GitHub repository secrets:

- `SUPABASE_URL`, `SUPABASE_SECRET_KEY`, and `GEMINI_API_KEY`.
- `ALLOWED_USER_ID`: configured sole-user UUID from verified Supabase Auth; use it to validate the worker's scan owner.

Use existing scanner defaults for non-secret settings unless deployment measurements justify a change. Secret values are entered directly in the providers' settings and never copied into chat, source, workflow inputs, result rows, or context documents. Vercel production dispatch credentials are configured for production only; preview deployments must not launch production scans. Local dispatch can be enabled deliberately for a controlled smoke test.

The GitHub API request uses a current, explicitly pinned API version and bounded request timeout. Accept the documented response for that version; successful dispatch means GitHub accepted a workflow, not that the scanner completed. Use a run name containing the scan UUID to correlate GitHub logs with Supabase without adding a database column.

## Workflow contract

Create `.github/workflows/scan.yml` with `workflow_dispatch` and one required string input, `scan_run_id`. The workflow must exist on the repository's default branch for manual dispatch availability. There are no scheduled, push-triggered, or pull-request-triggered scans.

- Use a standard Ubuntu GitHub-hosted runner; select a fixed supported image and Python version during planning.
- Pin third-party actions to verified commit SHAs, grant the workflow only contents read permission, and disable persisted checkout credentials.
- Install the Python package from the checkout with the project's lockfile after verifying its consistency. Editable installation makes the existing root prompt file available.
- Pass the scan UUID through an environment variable; never interpolate dispatch input into shell program text.
- Use a repository-wide scan concurrency group with `cancel-in-progress: false`, plus the Supabase active-scan lock and atomic claim. Workflow concurrency is supplementary; the database remains the authoritative lock.
- Do not add the deferred 30-minute timeout. The standard hosted runner's six-hour platform limit still applies; it is not unlimited execution.
- Do not automatically retry the scan or use GitHub's rerun feature as a replacement for Scan Now. A rerun of a non-queued scan must perform no scraping and must not overwrite its state.
- Keep generated listing data and audit reports out of GitHub artifacts. Persist application results only to Supabase. Avoid unnecessary caches initially to keep storage use simple.
- Provide a best-effort setup-failure finalizer only when checkout/installation/configuration fails before the worker step begins. It uses the same input/owner validation and conditionally marks only this scan's queued row failed. It never updates running or terminal stages. Once the worker step begins, ordinary failures are handled by the existing Python scan service; a failed or lost claim never triggers a workflow-level status overwrite. A small standard-library helper can make this conditional API update even when package installation failed, provided checkout succeeded; checkout failure cannot use that helper and relies on queued recovery.

## Failure and recovery behavior

Missing/invalid login returns 401; a validated but disallowed account returns 403. Reject cross-origin mutation requests and do not enable permissive CORS. Authenticate and authorize before using privileged Supabase operations.

A duplicate active scan returns 409 without dispatch. Missing configuration or unavailable dependencies returns a short 503 error without exposing provider bodies, tokens, or stack traces.

Distinguish definitive dispatch rejection from an ambiguous network outcome:

- If GitHub definitively rejects the request, conditionally mark the new scan failed only while it remains queued, set a safe error, and return 503.
- If the request times out, loses its response, or otherwise cannot prove rejection, preserve the queued row and return 202 with a safe notice that startup could not be confirmed. Do not retry automatically; GitHub may already have accepted it. Extend the frontend response handling to display that notice and refresh status.
- Never unconditionally mark a scan failed after dispatch; a runner may have claimed it already.

`POST /api/scan/recover` validates the same identity and origin rules, then atomically changes only an owner-scoped queued scan older than the configured threshold to failed. Keep the existing `data.recovered` and `data.scan` response. If a runner wins the claim first, recovery must leave it unchanged. If recovery wins first, a late runner exits without scraping.

The existing scanner writes safe errors for ordinary failures. Setup finalization is best-effort and cannot guarantee recovery after runner loss, force cancellation, timeout, or Supabase outage. The dashboard recovery button must never release scanning/evaluating/saving work based only on age. For a stranded running scan, inspect the corresponding GitHub run and confirm it has terminated before an owner-scoped administrative correction; this is a documented manual recovery step, not a new UI feature in this change.

## Product and retention behavior

Retain the Compact List interface, editable targets, Carousell thumbnail URLs and image fallback, single-user email/password login, and closed public registration. Queue/start delays are expected; progress reflects saved stages rather than a fabricated percentage of scraping work.

Keep the Supabase daily cleanup deleting scan rows older than three days with cascading listing/evaluation cleanup. Targets and the Auth user persist. The 72-hour cleanup rule does not become a frontend result filter. If cleanup removes the last completed scan, the frontend shows its existing empty state.

## Free-tier operation and policy

Vercel Hobby is for personal non-commercial use. Vercel runs the interface and dispatch requests; scraping runs entirely in GitHub Actions. Vercel's fair-use page lists scrapers as unsupported, so separating execution is a technical design choice and does not establish Vercel's approval of the application's overall purpose.

GitHub Free includes 2,000 runner minutes per month for private repositories. Standard hosted runners for public repositories have different free-use treatment, but this design assumes a private repository and does not authorize changing repository visibility. Allowance is shared with other workflows on the owner's account; installation time and failed runs also consume it.

Before the first hosted scan, verify the actual account allowance and configure Actions spending controls to stop paid overage. Keep standard runners and included storage limits. Do not enable paid plans, larger runners, paid storage, or Google Cloud billing. Vercel Hobby usage exhaustion can suspend functionality instead of providing paid capacity. Record measured scan duration after the controlled run before estimating sustainable frequency.

Sources checked 2026-10-02:

- [Vercel Hobby](https://vercel.com/docs/plans/hobby)
- [Vercel fair-use guidelines](https://vercel.com/docs/limits/fair-use-guidelines)
- [GitHub workflow dispatch API](https://docs.github.com/en/rest/actions/workflows#create-a-workflow-dispatch-event)
- [GitHub Actions limits](https://docs.github.com/en/actions/reference/limits)
- [GitHub Actions billing](https://docs.github.com/en/billing/concepts/product-billing/github-actions)

## Verification and rollout acceptance

Offline checks must cover identity/allowlist denial, same-origin enforcement, missing configuration, database active-scan conflict, dispatch acceptance/rejection/timeout, conditional failure updates, and recovery-versus-claim races. Worker tests must prove a wrong owner, malformed UUID, non-queued input, or lost claim performs no scraping and cannot fail a winner's scan. Test setup failure handling without changing terminal scans. Test that an ambiguous dispatch notice reloads scan status while retaining prior results.

Run the existing Python suite and frontend typecheck, lint, and production build after implementation. Inspect the production build for browser exposure of server credentials. Validate the workflow syntax and pinned dependencies/actions. Read the installed Next.js guides before changing frontend/server route code, as required by AGENTS.md.

Rollout requires the workflow on the correct branch, provider secrets entered privately, spending controls verified, Vercel production connected, and production Auth URL settings correct. Perform one controlled Scan Now run and verify its correlated Actions execution, stage updates, saved counts/results, thumbnail fallback, preserved target snapshot, and newest-completed result selection. Confirm a second click cannot create concurrent work. Record actual duration and any Carousell/Gemini access errors from the hosted runner without bypassing access controls.

The hosted rebuild remains incomplete until that run succeeds. This document records the design; implementation and deployment still await the appropriate review stages.
