# Deal Finder project instructions

## Context and coordination

- Read `project-context/context.md` for the codebase overview and current progress.
- Use `project-context/channel.md` to record task ownership, status, evidence, and handoffs.
- Lily's Codex project librarian definition is `.codex/agents/lily.toml`. Ask Lily to refresh context after architecture or workflow changes.
- Reusable project definitions for orchestration, workflow engineering, and release inspection are alongside Lily. Assign exact file ownership, avoid duplicate exploration, and escalate major user-action blockers promptly.
- Preserve existing work and coordinate overlapping file edits before making changes.

## Stack and structure

- Python >=3.10, a synchronous scanner/temporary CLI with a `src/deal_finder` package; Hatchling builds it. The hosted runner targets Python 3.12.
- Next.js/React frontend uses Node 24. Supabase is the sole supported persistence layer; Vercel hosts the UI/short API routes and GitHub Actions runs manual scans.
- `requests` and Beautiful Soup retrieve/parse Carousell pages; RapidFuzz matches candidates. Legacy `gspread` modules remain unused by the supported hosted flow.
- `pyproject.toml` registers `deal-finder = deal_finder.deal_finder:main`.
- `scan_job.py` validates runner UUIDs and allowed ownership; `scan_service.py` orchestrates queued claims/stages; `repository.py` and `supabase_repository.py` isolate storage. `deal_finder.py` retains the temporary CLI and legacy pipeline.
- `scraper.py` retrieves listings; `candidate_filter.py` applies initial gates; `deal_engine.py` combines candidate and audit decisions.
- `gemini_auditor.py` calls Gemini with `prompts/audit_v1.txt`; `models.py` defines data contracts and acceptance validation.
- `supabase/migrations/` contains the schema, owner RLS, one-active-scan rule, immutable snapshots, and backend three-day cleanup. The user manually ran the schema SQL; migration-history reconciliation is separate rollout work. Do not apply it twice.
- Sheets modules and Cloud Run source are legacy fallbacks, not the target architecture. Retire them only in a reviewed follow-up after hosted verification.

## Setup and commands

From the repository root in PowerShell:

```powershell
uv sync --locked
uv run --locked python -m pytest -q
uv run --locked python -m compileall -q src scripts
npm ci
npm run test:web
npm run typecheck
npm run lint
npm run build
```

- Configure local values using `.env.example`; `config.py` loads `.env` at import time and preserves existing environment values.
- The temporary CLI starts a Supabase scan using `SUPABASE_OWNER_ID`, or resumes queued work with `--scan-id`. The hosted job requires `SCAN_RUN_ID` and `ALLOWED_USER_ID`.
- The supported CLI no longer accepts `--audit` / `--dry-run`; the retained legacy `run_pipeline` can still contact Sheets/Carousell/Gemini. Neither path is an offline check.
- A real scan writes listings/evaluations/status to Supabase. Never run it without an explicitly controlled live-test request and verified spending controls.
- Optional wheel build: `uv build` (Hatchling backend). No dedicated Python lint/format command is configured.

## Code conventions

- Follow existing snake_case modules/functions, PascalCase classes, typed functions, dataclasses, and uppercase constants.
- Keep network/storage boundaries injectable where the surrounding code accepts callables or sessions.
- Use domain exceptions and existing CLI logging/error handling. Preserve secret redaction.
- Keep listing and model responses untrusted; preserve target, price, specification, accessory, and confidence validation.
- Normal publishing accepts validated Gemini deals; local fallback comparisons are included only when explicitly requested by audit mode.
- Keep credentials and runtime data out of source control and context documents.

## Verification and known gaps

- Pytest is configured with `tests/`, `src` on its import path, and a `live` marker.
- Python and web tests are present and tracked for publishing. The Python suite blocks unmocked Requests/socket network calls; workflow helpers use injected HTTP doubles. A `live` marker declaration alone does not implement live-test gating.
- Run checks and record actual current results; distinguish offline verification from hosted Auth/RLS/Actions acceptance. No local test or build proves production deployment.
- Inspect the current workflow rather than assuming it exists or has run. Manual dispatch/setup failure handling and paid-overage controls require independent verification.
- Recent commits mix short free-form messages with a merge commit; no enforced commit or PR policy was found.
- Verify documentation against source when changing behavior. Setup/secrets belong in provider dashboards, not source control or chat. Do not enable paid services, automatic scans/retries, or the deferred 30-minute application timeout.

<!-- BEGIN:nextjs-agent-rules -->

# This is NOT the Next.js you know

This version has breaking changes — APIs, conventions, and file structure may all differ from your training data. Read the relevant guide in `node_modules/next/dist/docs/` (resolved from this file's directory; in monorepos the `next` package may not be visible from the repo root) before writing any code. Heed deprecation notices.

This block is written and re-added by `next dev` — verify at `node_modules/next/dist/server/lib/generate-agent-files.js`. Removing it from a diff only re-creates the uncommitted change; committing it with your work keeps the tree clean.

<!-- END:nextjs-agent-rules -->
