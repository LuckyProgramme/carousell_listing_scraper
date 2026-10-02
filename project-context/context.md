# Carousell Deal Finder: project context

Maintainer: **Lily**, the context librarian defined in [`.codex/agents/lily.toml`](../.codex/agents/lily.toml). Last refreshed: **2026-10-02** by root as a fallback after review delegates reported usage-limit errors; Lily was notified without assigning overlapping edits. The remote implementation baseline was `96857a4`. Coordinate work in [channel.md](channel.md); consult [AGENTS.md](../AGENTS.md) for contributor instructions.

## Objective and progress

Current objective: replace the Google Sheets application boundary with a private personal-use web application whose sole persistence layer is Supabase, whose Python scan runs on demand in GitHub Actions, and whose frontend/short dispatch routes are hosted on Vercel Hobby. The user approved the [specification](../docs/superpowers/specs/2026-10-02-vercel-github-actions-design.md), [implementation plan](../docs/superpowers/plans/2026-10-02-vercel-github-actions-implementation.md), all remaining tasks, delegated coordination, and publication through a pull request. Tasks 1-8 are locally complete and published in [PR #2](https://github.com/LuckyProgramme/carousell_listing_scraper/pull/2), open and unmerged. Tasks 9-10 require merge authorization, private account setup and controlled hosted acceptance; `BUILD-001` remains active. Follow [the deployment guide](../docs/vercel-github-actions.md).

### Latest verification and rollout boundary

- Fresh final checks: **183 Python tests** and **150 web tests** pass; `uv lock --check`, Python `compileall`, typecheck, lint, production build with fake public values/empty privileged settings, and actionlint 1.7.12 pass. An isolated Python **3.12.14** `uv sync --locked --no-dev` installation succeeds and reads the checkout's audit prompt. No live audit was used for verification. The shared Python environment was preserved.
- Task 5 independently reviewed PASS before the later import-time error hardening; that hardening has two passing subprocess regressions. The orchestrator reviewed workflow/docs. The requested final independent re-review could not run because delegates reported usage-limit errors; root performed final integration checks. Do not describe the late changes as independently re-reviewed.
- Manual-only `.github/workflows/scan.yml` uses pinned checkout/setup-uv actions, Ubuntu 24.04/Python 3.12, repository-wide serialization, minimal permissions, no caches/artifacts/retries, and a setup-only conditional queued-failure helper. No 30-minute application timeout is added. Linux hosted execution is still unverified.
- Runner UUID/owner checks precede target reads; nonqueued reruns perform no work. Preclaim failures patch only the same owner's queued scan; lost/ambiguous claims do not fail another worker. Runtime imports stay inside safe error handling. Gemini validation, target snapshots, and thumbnail URLs remain covered by regressions.
- Read-only checks confirm the GitHub repository is public with default branch `main` and push access; preserve visibility. Vercel team `lesters-projects-c02f0b29` is accessible but empty. Connected tools cannot create/import a Vercel Git project or enter its environment variables, so those private setup steps require the user.
- Supabase remains healthy with expected schema/RLS/constraints/retention, one enabled owner target, and the confirmed sole user. Migration history is **empty** and needs a compared-schema baseline, not reapplication. Latest advisor observations include disabled leaked-password protection (WARN) and composite-FK/unused-index INFO findings; none was changed automatically.
- Before a hosted scan: publish/review/merge the PR; verify GitHub spending controls and the Gemini project's free-tier status; enter four GitHub secrets and production Vercel settings privately; obtain the actual production URL; configure Supabase Auth URLs; baseline migration history; then verify one controlled Scan Now. No deployment, scan, billing change, provider secret entry, or database write occurred during the local milestone.

- Completed: source reconnaissance, current architecture mapping, live workbook review, Supabase MCP connectivity check, target architecture decisions, and the frontend design prompt in [design.md](design.md).
- Implemented in the working tree: canonical records, a Supabase repository and schema migration, reusable scan orchestration, authenticated Cloud Run dispatcher/job entry points, a temporary Supabase-backed CLI, and the private Next.js Compact List frontend. The user manually ran the migration SQL against Supabase; the resulting live schema was then inspected read-only through MCP.
- Earlier Task 4 verification: both API routes returned JSON 403 for missing/foreign Origin, JSON 401 signed out, and GET 405 in local production HTTP checks. Mock-browser inspection of the actual Dashboard/CSS covered startup uncertainty, refresh/recovery races, stage polling, preserved results, and target navigation; captured console errors were empty. Local servers stopped. This is historical local evidence, not live Auth/RLS or hosted acceptance.
- Next: PR #2 review/merge authorization, private account setup, migration-history reconciliation, and one controlled hosted scan. Publication succeeded on `codex/vercel-github-actions-rollout` (application commit `273afee`); main was not changed. Writing-plans was unavailable, so the coordinator prepared the approved plan directly from the specification.

## Overview and stack

This working tree contains a private Next.js frontend plus Python services for an on-demand hosted Carousell scan. Supabase is the sole persistent store and its schema is live. Scan Now queues work and dispatches GitHub Actions through the server-only Vercel boundary; recovery uses the same validated identity/origin/deployment guards and owner-scoped stale-queue mutation. The dashboard displays startup notices, safely refreshes status, and preserves completed results on failed reads. Python orchestration retains scraper/filter/Gemini/validation behavior; the runner and workflow are locally ready, while hosted deployment remains pending.

[`pyproject.toml`](../pyproject.toml) specifies Python **>=3.10**, Hatchling packaging, and CLI, dispatcher, and scan-job entry points. Python dependencies include Requests, Beautiful Soup, RapidFuzz, Flask, Google Auth, and the legacy gspread modules. [`package.json`](../package.json) pins Next.js 16, React 19, Supabase browser/SSR clients, TypeScript, and ESLint. Gemini uses the REST `generateContent` endpoint directly rather than an SDK.

## Approved target architecture

The following decisions are approved for the rebuild. They supersede Google Sheets as the desired application architecture but do not imply that the current source already implements them.

- **Persistence:** Supabase is the only persistent store. The one-time migration imports current targets only; old listings, deals, and history are intentionally discarded. Targets remain until the user edits or deletes them.
- **Identity:** this is a single-user application for `dealfinder0322@gmail.com`, using Supabase email/password authentication. The confirmed live Auth user has UUID `749743db-c366-47c9-9373-bec966857b32`. Public registration and anonymous sign-ins are off; confirm-email is on and the email provider is enabled. Browser access must use a public/publishable client key plus row-level security; privileged Supabase credentials remain server-only.
- **Targets:** the authenticated user can add, edit, enable, disable, and delete targets in the frontend. A running scan uses a snapshot, so later edits affect only the next scan and do not rewrite stored evaluations.
- **Scan trigger:** scans run only when the user presses **Scan Now**. Only one scan may be active. There are no scheduled scans or automatic retries.
- **Execution (approved 2026-10-02):** authenticated, same-origin Vercel server routes create a queued Supabase scan and dispatch a fixed GitHub Actions workflow. The Python runner validates the scan UUID and sole-user ownership, atomically claims queued work, loads/snapshots targets, scrapes Carousell, runs deterministic matching and Gemini audit, then stores results/status in Supabase. Cloud Run remains implemented source, but is no longer the target deployment provider.
- **Frontend:** a private Next.js application intended for Vercel uses the approved **Compact List** direction in [design.md](design.md). It covers login, Dashboard, Targets, Results, scan progress/errors, and sign-out. Dashboard and Results deal/listing data load only from the newest completed scan; the newest overall scan independently drives current progress and status.
- **Listing images:** store Carousell thumbnail URLs, not copied image files. Compact result rows display the remote thumbnail and an accessible fallback when it cannot load.
- **Retention:** 72 hours is a Supabase backend cleanup rule only, not a frontend result window. The scheduled database cleanup removes scan runs older than three days and cascades to listings/evaluations; targets and the user account are excluded. The frontend shows results from the newest completed scan, even while a newer scan is queued, running, or failed.
- **Timeout:** do not add an application-enforced 30-minute scan limit during the initial build. Measure complete scans first; GitHub-hosted runner platform limits still apply.
- **Hosting and credentials:** personal, non-commercial Vercel Hobby use; GitHub Actions standard hosted runners with paid overage prevented by verified spending controls. Vercel needs a server-only Supabase secret and repository-scoped GitHub dispatch token; GitHub needs Supabase/Gemini secrets and the allowed owner UUID. Enter values privately. Vercel's fair-use restriction on scrapers remains a policy uncertainty even though scraping runs on GitHub. Do not enable paid services or Google Cloud billing.
- **Dispatch/recovery:** one active scan is enforced by Supabase. A definitive dispatch rejection conditionally fails only queued work; an ambiguous response preserves it without automatic retry. Recovery releases only an owner-scoped stale queued scan, never running work. The specification details setup-failure handling and manual investigation for stranded running scans.
- **CLI transition:** retain the CLI temporarily, but make it use Supabase rather than Sheets. Remove the CLI launcher only after the web workflow has been verified.

The approved intended flow is `Vercel UI/server dispatch -> GitHub Actions Python scan -> Supabase`, with the runner reusing the existing scraper, candidate filtering, Gemini audit, and independent acceptance validation. Canonical `Target`, `ScanRun`, `Listing`, and `Evaluation` records are provider-neutral; Google column names and Supabase row shapes belong at adapter boundaries. Tasks 1-8 have local verification only, not deployed behavior.

## Implemented hosted flow and safeguards

Both mutation routes now use the Vercel server boundary; neither depends on Cloud Run. The manual GitHub Actions workflow and safe startup helper are implemented and statically tested, but not hosted-run verified.

- [`app/api/scan/route.ts`](../app/api/scan/route.ts) is a Node POST handler calling `lib/scans/service.ts`. It validates `getUser()` identity/email, configured same-origin requests, and preview restrictions before creating owner-scoped queued work and dispatching a fixed repository/workflow/ref once. Accepted or ambiguous startup returns 202; ambiguity preserves queued work with a notice, and definitive rejection conditionally fails only the same owner's still-queued scan.
- [`lib/supabase/proxy.ts`](../lib/supabase/proxy.ts) passes exactly `/api/scan` and `/api/scan/recover` through so their handlers own request guards, validated identity, and JSON responses. Page/login gates retain their existing behavior.
- [`lib/scans/config.ts`](../lib/scans/config.ts), [`lib/supabase/admin.ts`](../lib/supabase/admin.ts), and [`lib/scans/repository.ts`](../lib/scans/repository.ts) provide typed request-time configuration, a lazy server-only admin client, and owner/status/cutoff-scoped queued mutations. Privileged sessions and mutation retries are disabled; requests are bounded at 10 seconds. Modern Supabase secrets use `apikey` rather than a copied Bearer secret. Only the exact active-scan constraint maps to 409.
- [`lib/scans/github.ts`](../lib/scans/github.ts) issues one bounded dispatch POST with API version `2026-03-10`; a valid 200 acceptance envelope is accepted, selected definitive refusals rejected, and uncertain responses/timeouts preserved without retry. [`vitest.config.mts`](../vitest.config.mts) uses a test-only server-only alias and a fake-credential/no-network harness. Recovery contracts now pass normally; isolated browser fixture scripts are documented in [`tests/web/manual/README.md`](../tests/web/manual/README.md) and render the actual Dashboard/CSS using fake data with `envDir: false`, without adding a production Auth bypass.
- [`lib/scans/recovery.ts`](../lib/scans/recovery.ts) uses storage-only configuration, so recovery works without GitHub credentials. It validates identity/origin/deployment, calculates a strict UTC cutoff (15 minutes default, valid range 5-1440), and calls the owner+queued+cutoff mutation. It returns `recovered` plus scan identity/status, preserves safe errors, and never updates running work.

1. [`app/page.tsx`](../app/page.tsx) authenticates the Supabase user, redirects non-allowed accounts to `/auth/denied`, fetches the newest overall scan for status, and separately fetches listings/evaluations only for the newest completed scan. The denied route signs the user out before returning to login.
2. [`components/dashboard-shell.tsx`](../components/dashboard-shell.tsx), [`lib/scans/client-actions.ts`](../lib/scans/client-actions.ts), and [`lib/scans/dashboard-data.ts`](../lib/scans/dashboard-data.ts) retain newest-completed results while status follows the newest scan. Actions display notices, clear busy in `finally`, send one POST without automatic retry, synchronously block duplicate clicks, and refresh after all attempts. Failed bounded snapshot reads preserve prior results and inhibit another scan until status is refreshed; **Refresh status** restores control. Active polling remains every 3.5 seconds, Release disappears for running stages, and Last scan follows completion.
3. [`app/api/scan/recover/route.ts`](../app/api/scan/recover/route.ts) is now a thin Node POST handler calling direct Vercel recovery; the old [`dispatcher.py`](../src/deal_finder/dispatcher.py) remains legacy source pending retirement in later plan tasks, not the frontend dispatch/recovery dependency.
4. [`scan_service.py`](../src/deal_finder/scan_service.py) claims a queued run, snapshots targets, updates lifecycle stages, saves outputs, and records safe failures. A lost or ambiguous atomic claim raises `ScanClaimError` and performs no failure-status update, preventing the losing worker from overwriting the winner's scan. Evaluation history uses immutable `target_snapshot_id` plus the snapshot body and nullable `target_id`, so deleting a target does not break an in-flight or retained evaluation.
5. [`20260930000000_hosted_deal_finder.sql`](../supabase/migrations/20260930000000_hosted_deal_finder.sql) defines owner-scoped RLS, one-active-scan enforcement, `target_id ... on delete set null`, immutable `target_snapshot_id`, uniqueness on `(listing_id, target_snapshot_id)` so one listing can retain decisions for multiple targets, and the scheduled three-day backend cleanup. The user manually ran this SQL; live read-only verification found the expected objects, but Supabase migration history is empty because it was not applied through migration tooling.
6. [`cloud-run-backend.md`](../docs/cloud-run-backend.md) documents the dispatcher/job boundary and the required `roles/run.jobsExecutorWithOverrides` role because the launch supplies a per-execution scan ID override.

## Architecture and execution flow

Production path: `Scan Now -> Vercel guarded dispatch -> GitHub Actions scan_job -> Supabase targets/snapshot -> scraping -> candidate filter -> Gemini audit -> independent validation -> Supabase outputs/status`. The older Sheets pipeline described below remains reusable legacy source, not the current CLI persistence path.

1. [`deal_finder.py`](../src/deal_finder/deal_finder.py), `main` and `run_pipeline`: parse `--audit`/`--dry-run`, configure redacted logging, orchestrate collaborators, and return counts or a shell failure status. Injected callables make the orchestration replaceable in offline tests.
2. [`sheets_handler.py`](../src/deal_finder/sheets_handler.py), `read_price_list_rows`: resolve headers by name and normalize price, target type, and bundle fields. Normal runs may initialize/extend `Price List`; audits require an existing readable tab.
3. [`scraper.py`](../src/deal_finder/scraper.py), `build_scrape_sources` and `scrape_price_list_sources`: validate unique item names and search modes, deduplicate source URLs, fetch/extract listings, and retain source/eligible-target metadata. Category mode uses configured category URLs; Item Name mode uses a target search. Parsing prefers structured JSON with an HTML fallback.
4. [`candidate_filter.py`](../src/deal_finder/candidate_filter.py), `find_candidate_matches`: apply accessory, lexical, and price gates. Placeholder/very-low prices remain triage candidates. [`deal_engine.py`](../src/deal_finder/deal_engine.py), `run_two_stage_cascade`, restricts matching to eligible targets and annotates the listing output.
5. [`gemini_auditor.py`](../src/deal_finder/gemini_auditor.py), `audit_batch`: send sequential structured-output chunks; validate IDs and permitted target names; isolate failed/malformed results into local fallback comparisons. [`prompts/audit_v1.txt`](../prompts/audit_v1.txt) supplies the audit contract, with marketplace text treated as untrusted data.
6. `run_two_stage_cascade` independently accepts Gemini deals only with a matching candidate, valid price, confidence >=80, matching specs, and no accessory classification. Bundles require opt-in, separate availability, and a source-backed individual price; `_verified_deal_price` verifies quoted evidence. At most one accepted Gemini deal is emitted per listing ID.
7. [`sheets_writer.py`](../src/deal_finder/sheets_writer.py), `write_outputs`: replace `Current Deals` and `All Listings`; `write_history` appends new listing IDs and updates known listings' last-seen dates. Audit mode instead writes `logs/audit_run_*.json` and includes eligible local fallback comparisons. Normal publishing excludes local fallback deals.

## Contracts and reusable patterns

- [`models.py`](../src/deal_finder/models.py): frozen `Listing`, `PriceListTarget`, `AuditResult`, and `ConfirmedDeal` dataclasses; `from_mapping`/`to_dict` bridge external dictionaries. Keep schema validation separate from deal acceptance gates.
- Price List columns include `Item Name`, `Category`, `Search Mode`, retail/deal prices in PHP, condition/freebie keywords, `Notes`, `Target Type`, and `Allow Bundle Check`. Missing/blank Search Mode defaults to Category; Target Type defaults to Hardware and also supports Game; bundle checking defaults false.
- `CandidateMatch` carries listing, target, effective price, lexical score, and price flag. `CascadeResult` carries deals, candidates, annotated listings, audit metadata, and source summaries.
- Snake-case modules/functions, PascalCase classes, type annotations, frozen dataclasses, and module constants recur. Integrations expose custom exception types and injectable HTTP/service collaborators; CLI-level errors produce logs and exit code 1.
- [`text_cleaner.py`](../src/deal_finder/text_cleaner.py), [`accessory_checker.py`](../src/deal_finder/accessory_checker.py), and [`variant_tokens.py`](../src/deal_finder/variant_tokens.py) provide reusable normalization, accessory, and variant matching helpers. Preserve the independent validation layer when changing the prompt.
- Recent commits have short descriptive messages and a merge commit; no reliable enforced branch, commit, or PR convention was established.

## Directory map and common commands

- `src/deal_finder/`: domain logic, scraper, Gemini, Supabase repository, scan orchestration, temporary CLI, dispatcher, job entry point, and legacy Sheets modules.
- `app/`, `components/`, `lib/`: Next.js routes, Compact List UI, Supabase clients, and frontend contracts.
- `supabase/migrations/`: versioned source for the live database schema, RLS, lifecycle constraints, and retention cleanup. Remote migration history is currently empty because the SQL was run manually.
- `docs/`: [current deployment guide](../docs/vercel-github-actions.md), approved specification/plan, and explicitly superseded Cloud Run documents. Tasks 1-8 are locally complete; hosted acceptance remains pending.
- `prompts/`: versioned semantic-audit prompt.
- `Screenshot-Results/`: example output screenshots; not executable tests.
- `project-context/`: overview/progress and subagent coordination; `.codex/agents/`: Lily's reusable definition.
- `.env.example`: configuration names/placeholders. [`config.py`](../src/deal_finder/config.py) loads root `.env` at import without overriding existing environment values. `logs/` is runtime-generated and ignored.
- [`find_deal.bat`](../find_deal.bat): Windows publishing launcher; selects a local console executable or `uv run deal-finder` and pauses afterward.

From the repository root, after choosing to prepare a local environment:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -e .
python -m pip install pytest
Copy-Item .env.example .env  # Only if .env does not already exist.
```

Use `uv sync --locked` and current [`README.md`](../README.md) for supported setup. Do not replace an existing environment file or supply Sheets credentials for the current Supabase-backed CLI. A real CLI run contacts Carousell/Gemini and writes runtime data; it is not an offline test.

- CLI help: `deal-finder --help` after installation.
- Audit/publish: consult current CLI help; the temporary CLI reads Supabase targets and executes the real scan. Neither audit nor normal mode is an offline validation command. Legacy Sheets helpers are not the supported persistence boundary.
- Source-layout alternative: set `$env:PYTHONPATH = "$PWD\src"`, then use `python -m deal_finder.deal_finder` with the same flags.
- Python checks: `uv run --locked python -m pytest -q -p no:cacheprovider --tb=short` passes 183 tests; `compileall -q src scripts` passes. The 31-test result is historical only.
- Frontend checks: `npm run test:web` (Vitest 5.0.3, pinned), `npm run typecheck`, `npm run lint`, and `npm run build`; root reports the 2026-10-02 results above. All 150 web tests now pass without expected-failing cases. [`eslint.config.mjs`](../eslint.config.mjs) excludes generated/dependency/Python paths so ESLint examines the frontend surface.
- Packaging uses Hatchling; a distribution build was not recorded in this milestone.

## Verified gaps and unresolved questions

- The offline Python suite blocks unmocked Requests/socket calls. Lock consistency and isolated locked Python 3.12 editable installation are verified; hosted Linux runtime, live credentials, and external-service compatibility are not.
- Config contains a nonempty default spreadsheet ID. Explicitly configure the intended destination before any live run; this document intentionally does not reproduce that ID.
- Hatchling force-includes the prompt into the wheel, and code prefers that packaged path with a checkout fallback. Editable prompt discovery is verified; a fresh installed-wheel runtime check is not part of this milestone.
- Existing untracked `REFACTORING_AND_CODE_REVIEW.md` was preserved. Its review claims were not used as verified evidence.
- **Live Supabase verification (read-only, 2026-09-30):** `targets`, `scan_runs`, `listings`, and `evaluations` exist in `public`. Current counts are one target and zero scan runs, listings, and evaluations. RLS is enabled on all four; expected owner policies and authenticated grants are present. The one-active-scan rule and `(listing_id, target_snapshot_id)` evaluation uniqueness are present. The daily retention cron is active at `17 3 * * *`. The security advisor returned no lints.
- **Auth verification:** `auth.users` contains exactly the intended confirmed user, `dealfinder0322@gmail.com` (`749743db-c366-47c9-9373-bec966857b32`). A read-only dashboard inspection confirmed **Allow new users to sign up** off, anonymous sign-ins off, confirm email on, and the email provider enabled.
- **Target cutover:** exactly one current target was imported from the public Price List range `B7:K8`: `legion 5`, Hardware, category `computers-tech`, Item Name search, bundle checks enabled, deal price PHP 60,000, retail price null, empty condition/freebie keywords and notes, and enabled status. Old scan/listing/evaluation history was not imported.
- **Migration tracking gap:** the remote migration history is empty because the user ran the SQL manually. Reconcile or baseline migration history before relying on automated migration status/diff workflows; do not reapply the schema blindly.
- **Performance advisor:** INFO-only findings reported three unindexed composite foreign keys plus unused indexes. The tables are empty, so unused-index observations are expected; review the composite-FK indexes against real query plans and data before changing them.
- GitHub dispatch, Vercel recovery, resilient dashboard feedback, Python runner, and workflow are locally implemented/tested. Account spending controls, free Gemini eligibility, private secrets/token, Vercel import, production Auth URLs, migration-history baseline, and a hosted end-to-end scan remain pending. Read-only workspace access is not a deployment. Cloud Run rollout is superseded by ARCH-002. Never record credentials or private service responses here.

## Ownership and maintenance

The onboarding objective created `project-context/context.md`, `project-context/channel.md`, `.codex/agents/lily.toml`, `AGENTS.md`, and the `CLAUDE.md` compatibility pointer. The approved UI prompt is in `project-context/design.md`. Application source, prompts, dependency/configuration files, existing review notes, and credential files remained outside Lily's edit scope during this refresh.

Lily owns context refreshes. The root coordinator owns the active end-to-end build until narrower scopes are assigned. Database/auth, Python runtime/GitHub Actions, and frontend/server-dispatch work must keep non-overlapping file ownership recorded in [channel.md](channel.md); an inspector should independently verify security boundaries, migrations, cleanup, and the complete Scan Now path before rollout.

Before new work, read this file and the channel, inspect `git status --short`, and recheck relevant source anchors. Record task ownership before edits. After a milestone, update verified facts, date/baseline, progress, checks actually run, blockers, and handoff. Separate observations from assumptions; never record secret values or claim an unexecuted check passed. Keep detailed task exchanges in the channel and accepted architectural facts here.
