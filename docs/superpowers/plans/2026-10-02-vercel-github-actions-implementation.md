# Vercel and GitHub Actions implementation plan

Date: 2026-10-02 (Asia/Manila)
Status: Tasks 1-8 locally implemented and verified. The user authorized all remaining tasks, orchestrated delegates, and publication through a pull request. Tasks 9-10 remain pending private account/secret setup and controlled hosted acceptance. No billing or automatic scan authority is inferred.
Design: [approved specification](../specs/2026-10-02-vercel-github-actions-design.md).

## Outcome and execution scope

Deliver one authenticated Scan Now request from Vercel that starts the existing Python scanner in GitHub Actions, saves progress/results to Supabase, and updates the existing Compact List dashboard. Use Vercel Hobby and standard GitHub runners with paid overage stopped. Preserve newest-completed results, three-day backend cleanup, target editing/snapshots, manual scans only, and the deferred 30-minute application timeout.

Recommended execution: implement sequentially in this chat, review each completed boundary, then perform account setup and one controlled production scan. Local implementation and external rollout are separate milestones. This plan authorizes neither deployment nor a paid service by itself; account actions and secret entry follow the user's rollout instructions. No new database schema is needed.

The requested writing-plans skill is absent from the local skills and plugin cache, so this plan was prepared directly from the approved specification. Existing uncommitted application work must be preserved; stage only reviewed task files when saving implementation commits.

## Evidence at the planning baseline (before Tasks 1-3)

- Both scan API routes currently forward to `CLOUD_RUN_DISPATCH_URL`; identity validation and launch currently live in the Python Flask dispatcher.
- `scan_job.main()` accepts `SCAN_RUN_ID` and calls `run_repository_scan`, but does not yet validate the configured sole-user UUID.
- The repository already supports atomic queued claim and stale queued recovery. Its general `update_scan()` is unconditional on status and must not be used to release work that another runner may have claimed.
- `run_repository_scan` currently loads targets before claiming. Its pre-claim failure update needs a conditional queued guard to satisfy the approved losing-worker safety requirement.
- Dashboard start/recovery handlers currently lack a `finally` block; transport failure can leave the button busy. They also always announce confirmed queue success on HTTP 202.
- Python tests exist, including claim-loss and target-snapshot coverage. No JavaScript test script is configured.
- Local Node is 24.19.0; uv is 0.11.24. Use Node 24 for web development/deployment and Python 3.12 on `ubuntu-24.04` for the scanner.
- Remote is `LuckyProgramme/carousell_listing_scraper`; local `origin/HEAD` points to `origin/main`. Verify the live default branch, visibility, access, and account limits during rollout; this local reference does not prove current remote settings.
- The Supabase schema/Auth/one-target state was previously verified. Migration history remains empty after manual SQL application. Do not recreate the account, reimport targets, or blindly apply the migration.

## Task 1: Add focused web tests and server boundaries

Files: `package.json`, `package-lock.json`, new `vitest.config.mts`, `tests/web/setup.ts`, `tests/web/scan-route.test.ts`, `tests/web/scan-recovery.test.ts`, and `tests/web/github-dispatch.test.ts`. The explicit ESM extension avoids the installed Vite native-loader warning; `tsconfig.json` includes it and ESLint includes the web tests.

1. Add a Node 24-compatible Vitest development dependency, pin the selected version exactly, and update the lockfile through npm. Add `test:web` invoking `vitest run`.
2. Configure Node test environment and the existing `@/` alias. Mock `server-only` and the cookie client in tests only; keep the production build's import protection intact.
3. Inject fetch, identity, scan persistence, and clock dependencies. Block unmocked outbound network access in these tests so the developer's `.env` cannot accidentally start a scan.
4. Write behavior tests before replacing the routes: invalid login, non-allowed user, wrong/missing origin, preview environment, missing configuration, active-scan conflict, accepted dispatch, definitive rejection, ambiguous dispatch, conditional failure, and stale recovery.
5. Test HTTP status and response shape at the actual route boundary as well as pure helpers. Assert denied requests cannot use the privileged repository or call GitHub.

Completion evidence: tests fail for the intended missing behavior, then pass as Tasks 2-4 are implemented. A passing test count alone does not establish production Auth or RLS.

## Task 2: Implement privileged queued-scan operations

Files: new `lib/supabase/admin.ts`, `lib/scans/repository.ts`, `lib/scans/config.ts`, and focused `tests/web/scan-repository.test.ts`.

1. Put `import "server-only"` in privileged modules. Build a Supabase admin client with session persistence/refresh disabled, using the existing public project URL and server-only `SUPABASE_SECRET_KEY`.
2. Validate configuration before writing a queued scan. For scan start, require explicit repository, workflow, branch, token, allowed email, and valid recovery threshold; recovery requires only identity/origin/storage/threshold configuration. Never accept configuration values from a browser request.
3. Provide narrow operations: create queued scan for a validated owner; fail a specified queued scan conditionally; recover that owner's queue older than a UTC cutoff. Keep filtering by owner and queued status in the same database mutation.
4. Map the active-scan uniqueness violation to 409 using the relevant constraint/error code; do not map every database conflict to an active scan.
5. Return safe domain errors and representation rows. An empty conditional update means the row is no longer eligible and must remain untouched.
6. Use bounded storage calls and no application-level mutation retry. If insertion response is lost, report storage uncertainty and reload status; do not insert a replacement or dispatch without a known scan ID.

Completion evidence: mocks verify exact owner/status/cutoff filters and race outcomes. No browser module imports the admin client, and missing secrets do not break a build that has no runtime scan request.

## Task 3: Replace Cloud Run scan dispatch

Files: new `lib/scans/auth.ts`, `lib/scans/github.ts`, `lib/scans/service.ts`; update `app/api/scan/route.ts` and Task 1 tests. The existing `lib/supabase/server.ts` accepts a bounded auth transport, and `lib/supabase/proxy.ts` passes only `/api/scan` through to its handler so login redirects do not mask JSON errors.

1. Read the installed Next.js route-handler, cookie, and server/client-boundary guides before editing route code. Use the Node runtime and POST-only handlers.
2. Validate `Origin` against the canonical production origin from trusted deployment configuration; allow explicit localhost development configuration. Reject absent or mismatched Origin and cross-site requests. Do not trust arbitrary forwarded host headers or add permissive CORS.
3. Reject scan mutations when `VERCEL_ENV` is preview/development; a local process with no Vercel environment can use explicitly configured local dispatch. Call Supabase `getUser()` and enforce the exact allowed email before privileged operations.
4. Call GitHub's fixed workflow dispatch endpoint once with `scan_run_id`. Use API version `2026-03-10`, JSON input, a 10-second outbound timeout, no-store fetch, and the fine-grained Actions token. Recheck the documented version contract at implementation time.
5. Accept successful documented dispatch responses without depending on returned run IDs; use the scan UUID in the workflow run name for correlation. Preserve `202 { data: { scan: { id, status } } }`.
6. For documented validation/auth/rate rejection responses that prove dispatch was refused, conditionally fail only the queued row and return a safe 503. Treat transport failure, timeout, server errors, or unknown/malformed acceptance responses as ambiguous; keep the queue, return 202 with `data.notice`, and never retry the dispatch automatically.
7. If a conditional failure update shows the worker already started, keep its state and return an accepted/in-progress notice. If failure persistence itself is unavailable, keep the user informed and leave recovery possible rather than overwriting status later.

Completion evidence: one create/one dispatch on success; no dispatch on denial/conflict; no second dispatch on timeout; no failure overwrite after a runner claims the scan. Provider bodies, request credentials, and raw exceptions are absent from responses.

## Task 4: Move recovery into Vercel and update dashboard feedback

Files: `app/api/scan/recover/route.ts`, `components/dashboard-shell.tsx`, optional small `lib/scans/client-actions.ts`, and corresponding web tests.

1. Apply the same validated user/origin/environment rules to recovery, using only storage configuration rather than requiring a working GitHub token.
2. Keep the 15-minute default queue threshold, validate the existing 5-1440-minute range, and issue a conditional owner/queued/created-at update. Return the existing `data.recovered` and `data.scan` shape.
3. Display `data.notice` for uncertain startup, then reload current status. Keep prior completed-scan results visible.
4. Wrap start/recovery transport and response handling in `try/catch/finally` so the button recovers after offline or invalid-response failures. After any potentially accepted start attempt, refresh scan state before permitting another click.
5. Keep stage polling, one-active-scan controls, target editing, and latest-completed selection intact. Do not add a GitHub control panel or technical details to the user interface.

Completion evidence: recent/running scans cannot be released, race losers are untouched, transport failure clears busy state, and ambiguous acceptance renders its notice. Manually inspect the dashboard using mocked responses for these states; the small client helper can be tested without adding a full browser-test framework.

## Task 5: Make Python execution safe for GitHub runners

Files: `src/deal_finder/scan_job.py`, `repository.py`, `supabase_repository.py`, `scan_service.py`; new `tests/test_scan_job.py`; extend repository/service tests.

1. Make scan-job messages provider-neutral. Require UUID-valued `SCAN_RUN_ID` and `ALLOWED_USER_ID`, check the scan owner, and reject non-queued or wrong-owner records before loading targets or calling the scraper.
2. Add `fail_queued_scan(scan_id, owner_id, safe_error)` to the repository boundary and REST adapter. It must conditionally patch only queued work, set completion time, and return no result when ineligible.
3. Use that conditional operation for target-load/validation failures before a claim. Once a claim succeeds, existing worker-owned stage/failure updates remain in place. Claim loss retains the existing no-write behavior.
4. Make errors and exit codes safe. A repeated execution for a completed/recovered/claimed scan exits without scraping or changing status; no scheduler retries it.
5. Test malformed/missing IDs, wrong owner, no targets, storage errors, recovered queue, rerun, ambiguous claim, and another worker winning while targets are being loaded. Assert no winner is failed and no rejected input reaches scraping/Gemini.
6. Preserve Gemini deal validation, target snapshots, saved listing thumbnails, and existing orchestration tests.

Completion evidence: focused Python tests and the full offline suite pass. All repository test doubles implement the new method. No live audit/scan is run as a unit-test check.

## Task 6: Add the manual GitHub Actions workflow

Files: new `.github/workflows/scan.yml`, `scripts/fail_queued_scan.py`, `tests/test_workflow_failure.py`, and `tests/test_scan_workflow.py`; update lockfile only if required.

1. Configure only `workflow_dispatch`, required `scan_run_id`, a run name containing that ID, contents read permission, and repository-wide scan concurrency with `cancel-in-progress: false`.
2. Use `ubuntu-24.04`, Python 3.12, and the inspected uv version 0.11.24 initially. Verify official checkout/setup-uv action release SHAs and compatibility before pinning them. Disable persisted checkout credentials and cache uploads.
3. Install Python through uv, use `uv sync --locked --no-dev --python 3.12`, then execute `.venv/bin/python -m deal_finder.scan_job`. Confirm editable prompt discovery works from the checkout. If the manifest/lock mismatch, refresh the lock and review the delta before restoring locked installation; never bypass the mismatch with `--frozen`.
4. Put dispatch inputs in environment variables, never shell interpolation. Scope Supabase/Gemini credentials to steps that require them. Validate required configuration before the worker step and avoid printing values.
5. Omit the deferred 30-minute timeout; retain GitHub's platform default. Add no scan schedule, automatic job retry, artifact upload, or paid runner.
6. Add a standard-library failure helper using HTTPS requests, bounded timeout, validated IDs/owner, and conditional queued update. It must handle modern Supabase secret headers correctly and never return provider bodies to logs.
7. Run the setup finalizer only after checkout succeeded and a setup/config step failed before the worker began. Check the worker step outcome explicitly. Worker failure/claim loss never invokes it. Checkout failure relies on the dashboard's queued recovery.
8. Validate YAML with a pinned actionlint release and test the finalizer with mocked HTTP. Use a YAML parser in test tooling if needed; pin it in the Python dev group. Assert manual-only trigger, standard runner, minimal permissions, concurrency, environment inputs, finalizer condition, and absence of a 30-minute timeout/artifacts.

Completion evidence: workflow static checks and helper tests pass, locked installation works, and no workflow run has been dispatched yet. Linux installation/runtime remains provisional until the controlled hosted run.

## Task 7: Update configuration and deployment documentation

Files: `.env.example`, `README.md`, new `docs/vercel-github-actions.md`, existing `docs/cloud-run-backend.md`, old hosted design/implementation documents, `package.json`, context documents through Lily.

1. Document every Vercel/GitHub setting from the spec, including Node 24, sole-user UUID, default branch, recovery threshold, production-only dispatch, and token expiry/rotation. Add a Node 24 engine declaration and retain npm's lockfile.
2. Mark Cloud Run guides and earlier deployment-plan sections as superseded, linking to the new guide. Remove Cloud Run environment variables from the supported setup example and explain the switch in README.
3. Preserve existing Cloud Run source/tests/Dockerfile as unused legacy files during this rollout. The new routes must contain no Cloud Run dependency. Defer deleting them and their dependencies until online verification, since some Google dependencies also support the legacy Sheets code.
4. Document queued recovery and investigation of stranded running scans: locate the exact scan ID run, establish that all corresponding executions have terminated, then conditionally correct only the owner-scoped non-terminal row. Never release running work based merely on age.
5. Document the manual-schema migration baseline separately. Reinspect remote schema/advisors/history and compare with the local SQL before marking the migration applied through the current CLI's documented repair command. Discover commands through help; do not execute the SQL again or claim baseline reconciliation has occurred.

Completion evidence: setup instructions match source/config names, no real secrets appear, active docs reference GitHub execution, and all relative links resolve. Legacy files are explicitly distinguished from the production path.

## Task 8: Complete local verification and handoff

Run after implementation, from repository root:

```powershell
uv lock --check
uv run --locked python -m pytest -q
uv run --locked python -m compileall -q src scripts
npm run test:web
npm run typecheck
npm run lint
npm run build
git diff --check
```

Use the verified actionlint executable on `.github/workflows/scan.yml`. Run a clean `npm ci` and locked Python installation in a separate task environment when needed to verify reproducibility without disturbing the user's running environment. Declare dependency-download permissions when required by the sandbox.

Inspect client chunks/import graphs for privileged module exposure; never print actual secret values. Exercise unauthenticated/disallowed/preview requests, queue conflicts, timeouts, claim/recovery races, and dashboard feedback with fake dependencies. Record actual commands, results, and known limitations. Do not reuse the historical 31-test result as fresh evidence.

Local acceptance: all approved security/failure contracts are covered, existing product behavior passes regression checks, and the production build succeeds. Present the reviewed file list, account setup checklist, and unresolved external configuration before rollout.

## Task 9: Account setup and production rollout

Ownership: root handles code/provider configuration within the user's authorization; user enters secret values privately and retains control of billing decisions.

1. Verify repository access, visibility, live default branch, Actions availability, and GitHub account free allowance. Preserve visibility. Inspect Actions spending controls and stop paid overage before any scan; never enable paid runners or storage.
2. Review/stage the required frontend/Python/workflow files, including existing untracked build files and lockfiles. Check ignored secrets and data before publishing. Make the workflow available on the verified default branch through the agreed Git workflow; do not push only the new YAML while the scanner/frontend remain absent remotely.
3. Guide the user to repository Actions secrets for `SUPABASE_URL`, `SUPABASE_SECRET_KEY`, `GEMINI_API_KEY`, and `ALLOWED_USER_ID`. Confirm names/presence without reading values.
4. Guide creation of an expiring fine-grained GitHub token limited to this repository with Actions write permission. The user enters it directly into Vercel production settings.
5. Import the repository into the user's Vercel Hobby project. Set the Next.js root/build defaults, Node 24, public Supabase settings, allowed email, server-only Supabase secret, repository/workflow/ref/token, and canonical frontend origin. Keep dispatch configuration out of preview environments and verify the runtime preview guard.
6. Deploy and obtain the actual production URL; configure `FRONTEND_ORIGIN` and Supabase Site URL/exact production redirect URLs, redeploy if needed, then verify login/sign-out and target access as the sole user.
7. Reconcile migration history by the read/compare/baseline procedure in Task 7. Verify cleanup remains active and targets are outside deletion; no destructive cleanup test on the live account.
8. Perform one controlled Scan Now run. Check the correlated Actions run, target snapshot, stage changes, counts, saved listings/evaluations, source links/thumbnails, and completed results. Verify a second request cannot create concurrent work. A completed zero-deal scan is valid if no listing passes the checks.
9. Confirm completed results remain visible when a subsequent queue/failure is simulated locally; do not launch unnecessary live scans for that check. Record hosted duration and actual quota usage so the later timeout decision has evidence.
10. If Carousell or Gemini rejects the hosted runner, report the observed error and stop that scan. Do not bypass access restrictions. Fix in-scope configuration before another explicitly controlled attempt.

Production acceptance: the one-click workflow succeeds end to end, secrets stay private, spending controls are verified, and results obey the approved display/retention rules. Account prerequisites and the first real scan are not satisfied by local tests alone.

## Task 10: Close the milestone and refresh context

Ask Lily, as required by AGENTS.md, to record the implemented architecture, actual check results, deployment status, measured scan duration, secret names only, migration-baseline status, and any remaining issues. Mark BUILD-001 complete only after production acceptance. Schedule no further scans or monitoring unless the user requests it.

Retire unused Cloud Run code/dependencies and the temporary CLI only in a reviewed follow-up after the web workflow is verified. Keep a useful fallback while the rollout is being proven.

## Planning review and external references

Self-review must verify Tasks 1-10 cover every design requirement, owner/status conditions appear in all privileged updates, uncertain dispatch never retries, no queued finalizer can overwrite a runner, and account steps occur after local verification. Fixed technical choices above are routine implementation decisions; current action/library release pins are verified when installed rather than invented in this document.

- Installed Next.js guides: `node_modules/next/dist/docs/01-app/01-getting-started/15-route-handlers.md` and `05-server-and-client-components.md`.
- [GitHub workflow dispatch](https://docs.github.com/en/rest/actions/workflows#create-a-workflow-dispatch-event)
- [uv GitHub Actions integration](https://docs.astral.sh/uv/guides/integration/github/)
- [uv locking and syncing](https://docs.astral.sh/uv/concepts/projects/sync/)
- [Vitest configuration](https://vitest.dev/guide/)
- [Vitest module mocking](https://vitest.dev/guide/mocking/modules)

Current execution boundary: Tasks 1-8 are locally complete: 183 Python and 150 web tests pass, lock consistency/compileall/typecheck/lint/fake-config production build/actionlint pass, and isolated Python 3.12.14 locked editable installation finds the audit prompt. Task 4 browser and local HTTP evidence remains historical, not a new production Auth/RLS check. Earlier Task 5 independent review passed before later subprocess error-hardening; the orchestrator reviewed Tasks 6-7, but final independent re-review was blocked by delegate usage-limit errors. Root completed integration verification. Publication through a PR is approved; no deployment, workflow dispatch, live database write, billing change, or secret entry has occurred. Next: PR review/merge, private account settings, migration-history baseline, production Auth and one controlled hosted scan. Do not mark the overall goal complete from local checks.
