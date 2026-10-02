# Deal Finder hosted application design

Date: 2026-09-30

> Historical design. The Cloud Run execution, dispatcher, credentials, and rollout sections were superseded on 2026-10-02 by the [approved Vercel/GitHub Actions specification](../superpowers/specs/2026-10-02-vercel-github-actions-design.md). Use the [current deployment guide](../vercel-github-actions.md). Other product decisions remain, but queued recovery never releases running work by age. This document is not authorization to deploy Cloud Run or rerun the Supabase SQL.

## Goal

Replace Google Sheets with a private, single-user web application. The user manages targets in the browser, starts scans manually, watches progress, and reviews recent results with Carousell thumbnails. Supabase is the only persistent store, Cloud Run executes the Python scanner, and Vercel hosts the Next.js interface.

The detailed visual brief is in [`project-context/design.md`](../../project-context/design.md). The selected interface is **Compact List**.

## Decisions

- Sole user: `dealfinder0322@gmail.com` through Supabase email/password authentication.
- No public registration after the account is provisioned.
- Scans run only after **Scan Now**; there is no scan schedule and no automatic retry.
- Only one scan may be queued or running for the user.
- Supabase replaces Sheets completely. Only the current targets are imported; old listings and history are not migrated.
- Scan-generated rows, including deals, raw listings, evaluations, status, errors, and history, are deleted after three days. Targets remain.
- Carousell images are displayed from their thumbnail URLs, with a fallback when loading fails. Images are not copied into Supabase Storage.
- No 30-minute application timeout is implemented initially. The Cloud Run timeout is chosen after measuring the completed pipeline.
- The CLI remains temporarily as a Supabase-backed fallback and is removed after the web flow is verified.

## System shape

1. The Next.js application signs the user in through Supabase and accesses owned rows through a publishable browser key and Row Level Security.
2. **Scan Now** sends the Supabase access token to a small Cloud Run dispatcher endpoint.
3. The dispatcher validates the token and exact allowed email, atomically creates one queued scan, and starts a Cloud Run Job with the scan and owner identifiers.
4. The job loads an immutable snapshot of enabled targets, runs the existing scraper and deal evaluation pipeline, writes canonical listing/evaluation records, and updates the scan state.
5. The frontend reads scan state and recent results from Supabase and updates the Compact List interface.

## Canonical records

### Target

An editable search definition owned by the user. It includes item name, category, search mode, retail and deal prices, condition keywords, freebie keywords, notes, target type, bundle permission, enabled state, and timestamps.

### ScanRun

One press of **Scan Now**. It stores owner, queued/running/completed/failed state, progress stage, timestamps, result counts, and a user-safe error message. A partial unique index prevents more than one queued/running scan per owner.

### Listing

A Carousell listing observed during a scan, including marketplace ID, title, price, seller facts, thumbnail URL, location, description, source link, and source timestamp. It belongs to a ScanRun and is removed through cascade cleanup.

### Evaluation

The relationship between a listing and a target decision. It stores the target snapshot, candidate and Gemini facts, final acceptance decision, confidence, issues, freebies, verified price, and savings. It belongs to a ScanRun and Listing.

## Security

- Enable RLS on every public table.
- Authenticated browser access is restricted to `owner_id = auth.uid()`.
- Index every owner column used by RLS.
- Target mutation is available only to the owning authenticated user.
- Cloud Run holds the Supabase service-role secret and Gemini key; neither is exposed to browser code.
- The dispatcher verifies the Supabase bearer token through the Auth API and rejects any email except the approved account.
- CORS is restricted to configured frontend origins.
- Service responses and database rows never expose secret values or raw stack traces.

## Retention

Supabase schedules a daily database function that deletes ScanRun rows older than three days. Foreign-key cascades remove their Listings and Evaluations. Targets and the Auth user are outside this cascade. The cleanup schedule is independent of scan scheduling.

## Failure behavior

- Dispatcher failures do not create duplicate active scans.
- A failed job writes a plain-language failure state when possible.
- Cloud Run job retries are disabled at deployment.
- The user explicitly presses **Try Again** to start another scan.
- A stale active scan can be marked failed through a protected recovery operation without silently launching a replacement.
- While status is queued, the Dashboard exposes that operation as **Release if stuck**; an ineligible recent queue is left unchanged.
- Thumbnail failures show a neutral fallback and do not hide the listing details or source link.

## Frontend

- Login screen with email and password only.
- Compact top navigation for Dashboard, Targets, Results, and Sign out.
- Dashboard heading and **Scan Now** action, with a narrow status panel beside recent results on desktop.
- Compact result rows with thumbnail, match facts, price, savings, and **View on Carousell**.
- Targets support add, edit, enable/disable, and confirmed deletion.
- Results switch between deals and all listings from only the newest completed scan. The newest overall scan independently drives current progress and errors.
- The three-day threshold is a Supabase cleanup rule, not a frontend history window.
- Responsive layouts stack the status panel and result rows on smaller screens.

## Cutover

The new schema, backend, Cloud Run image, and frontend are developed and verified together. A one-time target import populates Supabase. After an end-to-end scan succeeds, Sheets reads and writes are disabled, the web application becomes primary, and the temporary Supabase-backed CLI is removed in a later cleanup.
