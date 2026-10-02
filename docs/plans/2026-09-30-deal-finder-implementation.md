# Deal Finder hosted application implementation plan

Date: 2026-09-30

> Historical plan. Cloud Run workstreams and rollout steps were superseded on 2026-10-02 by the [Vercel/GitHub Actions implementation plan](../superpowers/plans/2026-10-02-vercel-github-actions-implementation.md). Use the [current deployment guide](../vercel-github-actions.md). The Supabase schema and sole Auth user already exist; do not recreate them or reapply the migration using this old plan. Retained Cloud Run files are unused legacy source, pending a reviewed cleanup after hosted verification.

## Completion criteria

- Supabase contains secure canonical Target, ScanRun, Listing, and Evaluation tables.
- The Python pipeline can run without Google Sheets and write complete results to Supabase.
- A protected Cloud Run dispatcher starts one job per manual request.
- The Next.js Compact List interface supports login, target management, Scan Now, progress, errors, and recent thumbnail results.
- Scan-generated rows expire after three days while targets remain.
- Local automated checks pass, a production build succeeds, and external rollout status is reported truthfully.

## Workstream 1: contracts and persistence seam

1. Extend domain records so target search mode and canonical scan/result values are typed rather than inferred from Sheet-shaped dictionaries.
2. Introduce repository protocols for targets, scan lifecycle, listings, and evaluations.
3. Adapt orchestration to accept repositories while preserving injectable scraper/auditor boundaries.
4. Keep a temporary CLI entry point that uses Supabase configuration.
5. Add unit tests for mapping, scan lifecycle, duplicate protection behavior, and failure handling.

## Workstream 2: Supabase schema

1. Add a versioned SQL migration under `supabase/migrations/`.
2. Create constrained tables, indexes, timestamps, and cascade relationships.
3. Enable RLS and owner policies for every exposed table.
4. Add the active-scan uniqueness rule and safe scan-start database function.
5. Add the three-day cleanup function and daily scheduled execution.
6. Apply the migration through Supabase MCP, inspect the resulting schema, and run security/performance advisors.
7. Generate frontend database types after the schema is live.

## Workstream 3: Python Supabase and Cloud Run services

1. Implement a server-only Supabase REST adapter using explicit environment configuration and redacted errors.
2. Add a Cloud Run job entry point that updates scan stages, takes a target snapshot, runs the pipeline, persists rows, and records safe failure details.
3. Add a small HTTP dispatcher with health and authenticated scan endpoints.
4. Validate the Supabase access token and enforce the approved email.
5. Start the Cloud Run Job through Google credentials without placing Google secrets in the frontend.
6. Add a production Dockerfile and deployment configuration notes. Leave the final Cloud Run timeout unset until measured.

## Workstream 4: Next.js Compact List frontend

1. Add a root Next.js application with Supabase browser/server clients and protected routes.
2. Build email/password login with no signup interface.
3. Build the Compact List shell and responsive styling from `project-context/design.md`.
4. Build target create/edit/enable/disable/delete flows with validation.
5. Build Scan Now and Try Again flows with duplicate prevention and clear stages.
6. Build results views for only the newest completed scan, with Carousell thumbnail URLs, accessible fallbacks, and source links; keep newest-scan progress separate.
7. Add loading, first-run, no-deal, expired-data, and failure states.
8. Add frontend lint/type/build checks.

## Workstream 5: target import and verification

1. Export only valid target rows from the current Sheet source without importing legacy listings or history.
2. Validate the records against the canonical Target contract before inserting.
3. Verify RLS as the authenticated user and verify unauthenticated denial.
4. Run Python unit tests, frontend checks, image fallback checks, and a local dispatcher/job simulation.
5. Run Supabase advisors after all schema changes.

## Workstream 6: rollout

1. The user provisions the sole Supabase Auth account and disables public signup without sharing the password.
2. Create or select a Google Cloud project under `dealfinder0322@gmail.com`. Stop and obtain the user's explicit approval before creating, linking, or changing any billing account. Only after that approval, enable required APIs and create least-privilege service identities.
3. Build and deploy the shared container as a Cloud Run service plus Cloud Run Job; disable automatic job retries.
4. Configure Cloud Run secrets and allowed frontend origins.
5. Connect Vercel MCP, link this repository, configure public Supabase values and the Cloud Run endpoint, then deploy the default branch.
6. Run one controlled production scan, measure its duration and resource use, and only then choose the Cloud Run timeout.
7. Confirm the three-day cleanup, thumbnail fallback, target editing, duplicate-scan prevention, and sign-out behavior.

## Known rollout gates

- Google Cloud CLI is not installed in the current workspace, so deployment will use an authenticated alternative or require setup later.
- Google Cloud billing is an explicit approval gate. No billing account may be created, linked, or changed without asking the user first.
- Vercel MCP is not currently available in this session; it must be connected before deployment.
- Private Supabase service-role and Gemini values are not read from local files and must be configured by the user through protected deployment secret controls.
- Supabase Auth account creation and password entry remain user-controlled.
