# Deploy Deal Finder with Vercel Hobby and GitHub Actions

This is the supported rollout guide, replacing Cloud Run. The website lives on Vercel, the scanner runs on a standard GitHub runner, and Supabase stores all application data. No Google Cloud project or billing setup is needed.

The [approved specification](superpowers/specs/2026-10-02-vercel-github-actions-design.md) and [implementation plan](superpowers/plans/2026-10-02-vercel-github-actions-implementation.md) are authoritative. Account setup and a successful controlled scan are separate from local code readiness. Secret values must be entered privately in the provider websites, never sent to an agent or committed.

## Before starting

The coordinator's read-only checks on 2026-10-02 found:

- GitHub repository `LuckyProgramme/carousell_listing_scraper` is **public**, its default branch is `main`, and the authenticated owner has push/admin access. Preserve visibility; “private app” means allowlisted website/data access, not a private Git repository.
- Vercel workspace **Lester's projects**, `lesters-projects-c02f0b29`, is accessible but had no projects. Importing and setting private values still requires the account owner. A connected MCP is not a deployed app.
- Supabase project `deal-finder` (`xxsizwurpgbapqrzyndo`) is healthy. Its existing schema matches the local migration contracts; migration history remains empty. The sole user's UUID is `749743db-c366-47c9-9373-bec966857b32`.
- Actual account spending controls, production login, and hosted scan execution are not yet verified. Do not launch a scan until those gates are closed.

Use the existing accounts. Do not create another Supabase project/user, reimport targets, change repository visibility, or turn on a paid plan.

## 1. Publish the reviewed application and workflow

Have the coordinator finish offline checks and independent inspection, then publish the **whole reviewed application** through the agreed pull request. A YAML-only push is insufficient: the frontend, Python package, prompts, scripts, tests, and both lockfiles must accompany it. Exclude credentials, `.env*` except `.env.example`, logs, cached dependencies, listing data, and unrelated local notes.

Merge the approved PR to `main` so [.github/workflows/scan.yml](../.github/workflows/scan.yml) exists on the default branch. This enables manual dispatch; it does not automatically scan. Keep `GITHUB_WORKFLOW_REF=main`. The workflow uses only `workflow_dispatch` with `scan_run_id`, `ubuntu-24.04`, Python 3.12, and uv 0.11.24. It has contents-read permission, no persisted checkout credentials/cache uploads, and one repository-wide scan concurrency group with cancellation disabled. The database lock remains authoritative.

Do not press GitHub's **Run workflow** or **Re-run jobs** as a substitute for Scan Now. No schedules, push/PR scan triggers, whole-scan retries, artifact uploads, larger runners, or application-enforced 30-minute timeout are part of this flow. Standard runner limits still apply. See [GitHub's runner limits](https://docs.github.com/en/actions/reference/limits).

## 2. Verify free-use and spending controls

Open the repository's **Settings → Actions → General** and confirm Actions is enabled with access to the pinned checkout/setup-uv actions. Keep standard runners. For this currently public repository, standard hosted runner use is free; the 2,000-minute GitHub Free allowance applies to private repositories, not this public runner path. Paid larger runners and storage are different products. Verify the owner's actual plan/usage rather than assuming all Actions features are free. [GitHub Actions billing](https://docs.github.com/en/billing/concepts/product-billing/github-actions).

In [GitHub account billing](https://github.com/settings/billing), inspect **Budgets and alerts**. Confirm the applicable Actions controls stop paid usage; an email alert alone is not a cap. For an account with payment details, use an applicable zero-paid-spend budget/hard-stop control if the UI supports it and verify the saved result. If zero or hard-stop behavior cannot be confirmed, stop and ask the coordinator before scanning. Do not add a payment method or enable paid runners/storage. [GitHub budget setup](https://docs.github.com/en/billing/how-tos/set-up-budgets).

Keep Vercel Hobby for personal, non-commercial use. Allowance exhaustion is not authorization to upgrade. Vercel's fair-use guidance lists scrapers as unsupported; running scraping on GitHub separates execution but does **not** prove Vercel approves the overall application. Treat any provider objection as a stop-and-review issue, not something to bypass. [Hobby plan](https://vercel.com/docs/plans/hobby), [fair-use guidance](https://vercel.com/docs/limits/fair-use-guidelines).

Gemini quota/cost is independent of hosting. Before the first live scan, privately check Google AI Studio's selected API key/project and confirm it is on the free tier: entering a key is not proof that requests are free. A key from a billing-enabled project may incur charges; earlier Google billing setup makes this a required human check. Do not run an API test or scan until free-tier status is confirmed, and do not enable paid Gemini/Google Cloud usage to overcome a limit. Record actual duration and quota use after the first successful scan.

## 3. Enter GitHub repository secrets

Open [the repository](https://github.com/LuckyProgramme/carousell_listing_scraper), then **Settings → Secrets and variables → Actions → New repository secret**. Add each name exactly:

| Name | Private value to enter |
| --- | --- |
| `SUPABASE_URL` | The existing project's HTTPS URL, from Supabase project settings. |
| `SUPABASE_SECRET_KEY` | The existing project's modern server secret key (`sb_secret_` prefix), not its publishable key. |
| `GEMINI_API_KEY` | Your existing Gemini key, entered directly here. |
| `ALLOWED_USER_ID` | `749743db-c366-47c9-9373-bec966857b32` |

Confirm names/presence only; nobody needs to retrieve or print values. `SCAN_RUN_ID` is supplied per request by the workflow input and is not a repository secret. Leave optional Gemini/scraper settings at the [configuration defaults](../.env.example) until measurements justify changes. Existing request-level Gemini timeout retry is not a retry of the whole scan.

## 4. Create the narrow dispatch token

In GitHub **Settings → Developer settings → Personal access tokens → Fine-grained tokens → Generate new token**:

1. Give it a clear name such as `Deal Finder Vercel dispatch` and a finite expiration (for example, 30 days).
2. Choose resource owner `LuckyProgramme` and **Only select repositories → carousell_listing_scraper**.
3. Grant repository **Actions: Read and write**. Keep other optional permissions off; read-only Metadata is implicit. Actions-write can do more than dispatch, so treat this as privileged.
4. Generate it and enter it directly as `GITHUB_ACTIONS_TOKEN` in Vercel **Production**. Do not paste it into chat or a local file. Record its expiry privately.

Before expiration, create a replacement with the same narrow scope, replace the Production value, redeploy, and revoke the old token after confirming dispatch works. A revoked/expired token prevents new starts but is not a reason to rerun a scan. [GitHub token guidance](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens), [dispatch permissions/API](https://docs.github.com/en/rest/actions/workflows#create-a-workflow-dispatch-event).

## 5. Import the website into Vercel

Open [Lester's projects](https://vercel.com/lesters-projects-c02f0b29). Select **Add New → Project**, connect the GitHub owner account if requested, and import `LuckyProgramme/carousell_listing_scraper`. If it is absent, grant the Vercel GitHub integration access to this repository; do not import a different copy.

Select these settings:

| Setting | Value |
| --- | --- |
| Framework | Next.js |
| Root Directory | Repository root (`.`), not `src`, `app`, or a nested Windows folder. |
| Production branch | `main` |
| Node.js | `24.x` (also declared in `package.json`). |
| Install command | `npm ci` |
| Build command | `npm run build` |
| Output Directory | Next.js default; do not override to `out` or a Python directory. |
| Plan | Existing Hobby; no paid add-ons. |

This project uses Vercel's Git integration, not an extra Actions workflow to deploy Vercel. [Git import](https://vercel.com/docs/git), [Node versions/engine setting](https://vercel.com/docs/functions/runtimes/node-js/node-js-versions).

In the project's **Settings → Environment Variables**, add the following with **Production** selected only:

| Name | Value |
| --- | --- |
| `NEXT_PUBLIC_SUPABASE_URL` | Existing Supabase HTTPS project URL. |
| `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY` | Existing public/publishable key; safe for the browser. |
| `ALLOWED_USER_EMAIL` | `dealfinder0322@gmail.com` |
| `SUPABASE_SECRET_KEY` | Modern server-only secret from step 3; never `NEXT_PUBLIC_`. |
| `GITHUB_ACTIONS_TOKEN` | Expiring token from step 4, entered privately. |
| `GITHUB_REPOSITORY` | `LuckyProgramme/carousell_listing_scraper` |
| `GITHUB_WORKFLOW_FILE` | `scan.yml` |
| `GITHUB_WORKFLOW_REF` | `main` |
| `STALE_QUEUED_SCAN_MINUTES` | `15` (valid integer range 5–1440). |
| `FRONTEND_ORIGIN` | Exact canonical HTTPS production origin, e.g. `https://your-project.vercel.app`; no trailing slash, path, query, or fragment. |

Use sensitive/hidden storage for the two private secrets where the dashboard supports it. Vercel does **not** need `GEMINI_API_KEY`, `ALLOWED_USER_ID`, `SUPABASE_URL`, or Google Cloud values. Its server storage client reads `NEXT_PUBLIC_SUPABASE_URL`, while the Python runner reads `SUPABASE_URL`.

If the production hostname is not known at import, deploy once with only the public Supabase settings and allowed email; keep Scan Now unused. After Vercel assigns the stable production URL, add the remaining Production settings with that exact `FRONTEND_ORIGIN` and redeploy. A missing scan setting returns a safe error without queuing work. A one-off preview/deployment URL is not the canonical production origin.

Do not copy production dispatch credentials to Preview or Development. Public read settings may be supplied separately if previews are needed, but no production admin/dispatch key belongs there. The runtime guard denies scan mutations in Vercel preview/development even if secrets were accidentally supplied. Changing environment values affects new deployments: redeploy Production after changes, including public values compiled into the browser bundle. [Vercel environment variables](https://vercel.com/docs/environment-variables).

## 6. Set Supabase Auth URLs and check login

In the existing Supabase project's **Authentication → URL Configuration**, set **Site URL** to the actual canonical production HTTPS URL. Add only exact production redirect URLs needed by this app (`https://your-project.vercel.app/` and `https://your-project.vercel.app/login`), replacing the sample hostname. Do not add a wildcard for all Vercel previews. This version uses email/password login, not OAuth, and has no `/auth/callback` or `/auth/confirm` handler; do not invent one in the settings. [Supabase redirect guidance](https://supabase.com/docs/guides/auth/redirect-urls).

Keep public signup and anonymous sign-in off, email/password enabled, and the existing account confirmed. Sign in as `dealfinder0322@gmail.com` without sharing its password. Confirm Dashboard/Targets load, enabled targets can be edited, sign-out returns to login, and signed-out mutation requests fail. Recheck fresh production Auth/RLS; an earlier read-only dashboard inspection is not a production login test.

## Migration-history baseline: separate administrative gate

The SQL was run manually, so the live schema exists but `supabase_migrations.schema_migrations` still has no recorded migration. The coordinator's 2026-10-02 read-only inspection found the four table definitions/constraints/indexes, owner RLS/grants, update triggers, private functions, and cleanup cron consistent with [the local SQL](../supabase/migrations/20260930000000_hosted_deal_finder.sql). Cleanup is active daily at `17 3 * * *` and cascades only scan-generated data older than three days; targets and Auth persist. Security reported disabled leaked-password protection; performance reported three missing composite-FK covering indexes and eight unused indexes. These observations do not authorize a paid Auth upgrade or unrelated schema work.

Do not run the SQL again, `db push`, `migration up`, or a database reset against this live project to fill history. Baseline repair changes bookkeeping, not the actual schema. The CLI is not installed in the inspected workspace and database/CLI authentication is not configured, so repair is **not done**.

For the eventual administrative session:

1. Install a current supported Supabase CLI through the [official installation guide](https://supabase.com/docs/guides/local-development/cli/getting-started), then discover commands before use:

   ```powershell
   supabase --version
   supabase --help
   supabase link --help
   supabase migration --help
   supabase migration list --help
   supabase migration repair --help
   ```

2. Confirm the installed help matches the [current repair reference](https://supabase.com/docs/reference/cli/supabase-migration-repair). Authenticate/link the intended project privately using the installed help; use a scoped personal access token rather than exposing broad credentials. Do not pass passwords/tokens in visible command text or logs.
3. Re-read remote schema, policies/grants/functions/indexes, security/performance advisors, cron, and migration history; compare every local SQL contract. If anything differs, stop and reconcile the discrepancy before marking a version applied. Listing timestamps alone does not prove schema equality.
4. Only after that proof and administrator approval, the documented command form is `supabase migration repair 20260930000000 --status applied --linked`. Confirm this form in the installed help before executing it. It records this existing version as applied; it does not execute its SQL. Then use the verified `supabase migration list --linked` command and read-only history inspection to confirm the matching entry. [Migration tracking and repair](https://supabase.com/docs/guides/deployment/database-migrations).

Record the actual repair result separately from the schema inspection. No SQL/baseline mutation is part of this documentation task. New tables need explicit Data API grants plus RLS; existing grants do not disappear solely because of the announced default-privilege change. [Supabase Data API change](https://supabase.com/changelog/45329-breaking-change-tables-not-exposed-to-data-and-graphql-api-automatically).

## 7. Run one controlled Scan Now test

After code, private secrets, spending controls, production origin/Auth, and the baseline gate are ready:

1. Sign in, confirm at least one enabled target, and press **Scan Now once**.
2. Note the scan UUID. In repository **Actions**, correlate the run name containing that exact UUID. GitHub acceptance is not scan completion.
3. Follow Supabase/dashboard stages: `queued → scanning → evaluating → saving → completed`, or a safe `failed` state. Confirm the stored target snapshot, counts, listings/evaluations, source links, thumbnail/fallback, and newest-completed result selection. A completed scan with zero deals is valid if nothing passes validation.
4. Confirm a second request cannot start concurrent work. Use local simulations for later queue/failure preservation instead of launching extra live scans unnecessarily.
5. Record elapsed setup/scan duration and quota use. Do not choose a final timeout before measuring. If Carousell or Gemini refuses the hosted runner, inspect the safe error and stop; do not bypass access restrictions or auto-retry.

Only a successful correlated Actions execution and displayed saved result proves online acceptance. Offline tests/static lint/build, a deployed login screen, or a green installation step alone do not.

## Recovery and operations

**Queued:** startup uncertainty intentionally preserves a queue because GitHub may already have accepted the request. Reload status; do not repeatedly click Scan Now. After the configured age (15 minutes by default), use **Release if stuck**. `POST /api/scan/recover` authenticates the same user/origin and atomically filters by owner, `status=queued`, and the strict UTC cutoff. If a worker claims first, recovery leaves it alone; if recovery wins, a late runner does no scraping. Recovery needs storage/identity configuration, not a working GitHub token.

**Setup failure:** configuration is validated offline using `python3 scripts/fail_queued_scan.py --validate-only`; the worker uses `.venv/bin/python -m deal_finder.scan_job`. Only checkout success plus a named setup/configuration failure with the worker skipped enables the best-effort helper, which can fail only this owner's still-queued row. Checkout failure, abrupt runner loss, force cancellation, and storage outage can require manual investigation/recovery. Cancellation and worker failures/claim loss never trigger a workflow-level overwrite. Do not re-run an existing scan to recover it.

**Apparently stranded running:** the UI deliberately cannot release `scanning`, `evaluating`, or `saving` by age. Ask the coordinator/admin to locate the **exact scan UUID** and inspect all corresponding runs, attempts/reruns, jobs, and executions. Confirm all are terminal and no worker can still write. If any execution is queued/running or evidence is uncertain, do not change the row. After terminal proof, a reviewed administrative correction must filter the exact scan ID, allowed owner UUID, and exact observed non-terminal status in the same mutation, set a safe failure and UTC completion timestamp, and verify the returned row. If it changed concurrently or zero rows match, stop and reread. Never use a broad, unowned, age-only, or unconditional running update.

**Retention:** daily cleanup removes scan-generated rows after three days, independently of manual scanning. Do not test cleanup destructively on the live account. Previous completed results remain visible while a newer scan is running/failed until cleanup removes them; then the normal empty state appears.

**Credentials:** rotate disclosed or expiring keys privately, replace only their provider settings, and redeploy Vercel when its values change. Modern Supabase secrets belong in the `apikey` header, not a copied `Authorization: Bearer` secret; the adapters/helpers implement this. Legacy service-role JWT compatibility is not the supported Vercel setup. No secret or raw listing/audit payload should be uploaded as an Actions artifact.

## Retained legacy source

The [old Cloud Run guide](cloud-run-backend.md), [original hosted design](plans/2026-09-30-deal-finder-hosted-design.md), and [original implementation plan](plans/2026-09-30-deal-finder-implementation.md) are historical. Dispatcher, Dockerfile, Flask/Gunicorn/Google dependencies, and Sheets compatibility modules remain unused by the supported web flow. The temporary Supabase CLI also remains until hosted verification. Their deletion is a separate reviewed follow-up, not a prerequisite for this rollout.
