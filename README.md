# Deal Finder

A private, single-user website that finds price-qualified Carousell listings, applies deterministic safety checks, asks Gemini to audit likely matches, and stores results in Supabase.

## Supported architecture

- Next.js on Vercel Hobby provides email/password login, editable targets, Scan Now, progress, and Compact List results. Short server routes dispatch work; Vercel does not run the scraper.
- GitHub Actions runs the Python scanner only after Scan Now. The manual workflow is [scan.yml](.github/workflows/scan.yml).
- Supabase is the only application persistence layer. Owner-scoped Row Level Security protects browser reads and target edits; private server keys handle scan writes.
- Gemini audits candidates inside the runner. Its key never reaches the browser or Vercel.

Use the [step-by-step deployment guide](docs/vercel-github-actions.md) for provider settings, private secret entry, account gates, and recovery. The [approved specification](docs/superpowers/specs/2026-10-02-vercel-github-actions-design.md) and [implementation plan](docs/superpowers/plans/2026-10-02-vercel-github-actions-implementation.md) record the agreed scope. Local checks do not prove that production login or a hosted scan works; that requires one controlled end-to-end run.

Scans are manual, one can be active at a time, and whole scans are not automatically retried. There is no application-enforced 30-minute scan limit; measure the first complete scan before choosing one. GitHub platform limits still apply. Do not enable paid plans, larger runners, storage overage, or Google Cloud billing. Vercel Hobby is personal/non-commercial, and its scraper policy remains a caveat discussed in the guide.

## Local setup

Use Node.js **24.x**, Python **3.12**, and uv **0.11.24** for the deployment-matching environment. The Python package supports >=3.10, but the hosted workflow uses 3.12. Install from the checked-in lockfiles:

```powershell
uv sync --locked --python 3.12
npm ci
```

For Next.js, create `.env.local` only if it does not already exist. Copy just these names from [.env.example](.env.example) and fill them privately:

```env
NEXT_PUBLIC_SUPABASE_URL=https://your-project-ref.supabase.co
NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY=
ALLOWED_USER_EMAIL=dealfinder0322@gmail.com
```

Run `npm run dev` and open `http://localhost:3000`. Login and target access need the existing Supabase account/project. The scan routes additionally need the server settings in the deployment guide, including explicit `FRONTEND_ORIGIN=http://localhost:3000`. Supplying those settings locally can dispatch a real hosted scan; do so only deliberately after the rollout gates. Missing scan configuration fails safely rather than launching a scanner.

Python reads root `.env`; Next.js reads `.env.local`. Neither file belongs in Git. Do not overwrite an existing file with a downloaded provider configuration. No local credential file is needed for offline unit tests.

## Database and product behavior

[20260930000000_hosted_deal_finder.sql](supabase/migrations/20260930000000_hosted_deal_finder.sql) defines `targets`, `scan_runs`, `listings`, and `evaluations`, RLS, the one-active-scan index, immutable target snapshots, and daily three-day cleanup. The user already applied this SQL manually. The live schema has been inspected, but migration history is still empty; follow the guide's separate [baseline procedure](docs/vercel-github-actions.md#migration-history-baseline-separate-administrative-gate), not another SQL application or `db push`.

- Only `dealfinder0322@gmail.com` is allowed. Public registration and anonymous login must remain off. Do not recreate the existing confirmed Auth user or reimport the existing target.
- Targets can be added, edited, enabled, disabled, or deleted. Targets are snapshotted when a queued scan is claimed; edits after that affect the next scan.
- Dashboard status follows the newest scan. Deals and All Listings show only the newest completed scan, even when a newer scan is queued, running, or failed.
- Listing rows display remote Carousell thumbnail URLs and an accessible fallback; pictures are not copied into Supabase Storage.
- **Release if stuck** changes only the owner's queued scan older than the configured threshold (15 minutes by default). It never interrupts scanning, evaluating, or saving work. Running recovery requires the guide's manual investigation.
- The daily database cleanup removes scans older than three days and their listings/evaluations. Targets and the Auth user remain. This 72-hour rule is backend cleanup, not a frontend result filter.

## Offline checks

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

Validate `.github/workflows/scan.yml` with the verified/pinned actionlint executable described by the rollout coordinator. Python/web tests use fake boundaries and block unmocked network requests. A test result is not proof of hosted Linux execution, production Auth/RLS, or live Carousell/Gemini access. `npm run build` needs public Supabase configuration; privileged scan settings are read at request time and are not needed for a compile-only build.

The isolated [manual Dashboard fixture](tests/web/manual/README.md) renders the actual UI with fake data over a local HTTP preview. Opening its HTML directly as a `file://` URL does not compile its TypeScript and is not a production login bypass.

## Temporary and legacy files

The temporary **Supabase-backed CLI** (`deal-finder`, [find_deal.bat](find_deal.bat)) remains until the web workflow is verified. It requires `SUPABASE_OWNER_ID` plus private Supabase/Gemini configuration and starts real work; it is not an offline check. The hosted worker uses `python -m deal_finder.scan_job` with workflow-supplied `SCAN_RUN_ID` and configured `ALLOWED_USER_ID`, not the local CLI launcher.

[dispatcher.py](src/deal_finder/dispatcher.py), [Dockerfile](Dockerfile), and the [Cloud Run guide](docs/cloud-run-backend.md) are retained unused legacy source. The new web scan/recovery routes do not call them. Flask, Gunicorn, and Google dependencies are not retired in this rollout; some Google libraries also support the legacy Sheets modules. `sheets_handler.py`, `sheets_writer.py`, and the older Sheets `run_pipeline` path remain compatibility source, not the supported hosted persistence path. Do not run that legacy path as a verification command. Remove legacy code/dependencies and the temporary CLI only in a reviewed follow-up after online acceptance.

## Security

Never put `SUPABASE_SECRET_KEY`, `GITHUB_ACTIONS_TOKEN`, or `GEMINI_API_KEY` in a `NEXT_PUBLIC_*` variable. Enter production keys directly in protected provider settings; never paste them into chat, code, workflow inputs, logs, or result rows. Vercel Production has the dispatch token and server-only Supabase secret; GitHub Actions has Supabase/Gemini secrets. Preview deployments must not have production dispatch credentials and are blocked by the runtime guard.

Marketplace text and model output are untrusted. Existing independent price, specification, accessory, confidence, and bundle checks still decide acceptance. Safe user errors omit provider payloads and stack traces. Rotate any disclosed credential promptly; deleting it from a file does not remove Git history.
