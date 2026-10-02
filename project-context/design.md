# Deal Finder frontend design prompt

## Product goal

Design a private, responsive Deal Finder web application for one user. Keep the interface calm, direct, and easy to understand for a non-technical owner. The main action is **Scan Now**. Avoid dense admin-dashboard styling, decorative charts, gradients, oversized headings, or unnecessary settings.

## Selected interface direction: Compact List

- Use a compact top navigation with Dashboard, Targets, and Results rather than a permanent desktop sidebar.
- Place the page heading and **Scan Now** action on one clear top row.
- On desktop, use a narrow scan-status panel beside a wider recent-results list.
- Present deals as compact listing rows with the thumbnail on the left, key facts in the middle, and price, savings, and the Carousell action on the right.
- Stack the scan-status panel above the results on smaller screens.
- This direction supersedes the Calm Grid and Scan Focus concepts from the design exploration.

## Visual direction

- Use a warm neutral background, solid white or near-black surfaces, restrained green for the primary action, and amber only for savings or attention states.
- Use a clean sans-serif typeface with medium-weight headings and comfortable spacing.
- Use compact top navigation at every size, reducing its contents on smaller screens.
- Use flat surfaces, subtle borders, moderate corner rounding, and no decorative shadows.
- Keep the primary action visually dominant without making the page feel promotional.
- Meet accessible contrast, keyboard navigation, visible focus, and mobile touch-target requirements.

## Application structure

### Login

- Show a small Deal Finder wordmark, email field, password field, **Sign in** button, and clear error text.
- Do not show public registration or social login.
- Only the pre-created `dealfinder0322@gmail.com` account can access the application.

### Dashboard

- Show the page title, last scan time, and a single prominent **Scan Now** button.
- Show one compact status area with these stages: Queued, Scanning, Evaluating, Saving, and Completed.
- While a scan is active, disable the Scan Now button and prevent a second scan.
- Show small result counts for listings checked, candidates evaluated, and deals found.
- Show errors in plain language with a **Try Again** action. Never expose credentials, stack traces, or raw service responses.
- While a scan is queued, show **Release if stuck**. The protected check releases only an eligible stale queued scan and never interrupts a running scan.
- Display recent deals as compact responsive listing rows with thumbnails.

### Listing card

- Put the Carousell thumbnail on the left on desktop and tablet, then above or at the upper-left of the details on narrow phones.
- Load the image from the stored Carousell thumbnail URL. If it fails, display a neutral product-image placeholder.
- Show listing title, price, expected savings, matched target, confidence, condition, issues, and freebies when available.
- Include a clearly labeled **View on Carousell** link that opens the original listing.
- Do not copy thumbnail files into Supabase Storage in the initial build.

### Targets

- List every search target with item name, category, search mode, deal price, retail price, target type, and enabled state.
- Provide **Add target**, **Edit**, **Enable/Disable**, and confirmed **Delete** actions.
- The edit form includes condition-downsizing keywords, freebie keywords, notes, and bundle-check permission.
- Validate required fields and positive prices before saving.
- Target changes apply to the next scan. A scan already running continues with the target snapshot it started with.

### Results

- Show deals and all listings from only the newest completed scan.
- Keep the newest overall scan separate for progress and errors, so a newer active or failed scan does not replace the completed results.
- Treat the 72-hour period as a Supabase cleanup policy, not a frontend results window.
- Allow the user to switch between Deals and All listings without creating a separate analytics dashboard.
- Show the newest completed scan's completion time and counts.
- Keep historical target values with each evaluation so later target edits do not rewrite previous results.

### Account controls

- Show the signed-in email and a **Sign out** action.
- Do not add team management, invitations, roles, billing controls, or public profiles.

## Data and runtime behavior

- Supabase is the only persistent data store.
- Cloud Run performs scans only after the user presses **Scan Now**.
- There are no scheduled scans and no automatic scan retries.
- Do not enforce a 30-minute timeout in application code during the initial build. Keep the Cloud Run timeout as a deployment decision after real scan duration is measured.
- Automatically delete raw listings, evaluations, deals, scan status, errors, and scan history after three days. Never delete targets or the user account during cleanup.
- The frontend uses Supabase email/password authentication and row-level security.
- Private Supabase, Google Cloud, and Gemini credentials are server-only and must never appear in browser code.

## Responsive behavior

- Desktop: compact top navigation, scan controls at the top, a narrow scan-status panel, and a wider list of thumbnail result rows.
- Tablet: compact top navigation with the scan-status panel stacked above the result list.
- Mobile: simplified navigation, full-width actions, and one-column listing rows with large touch controls.
- Do not require horizontal scrolling for ordinary content.

## Empty, loading, and failure states

- Before the first scan, explain that Scan Now searches the enabled targets.
- Use lightweight skeletons while loading saved data.
- For a scan with no deals, say that the scan completed successfully and no qualifying deals were found.
- When a thumbnail fails, keep the listing card usable with a placeholder.
- When Cloud Run fails, preserve a safe failure message until the user retries or the three-day cleanup removes it.

## Initial implementation boundary

- Build the login, dashboard, targets, results, listing cards, scan progress, and failure states described above.
- Do not add charts, notifications, scheduled scans, team features, image uploads, copied marketplace images, or advanced filters.
- Keep UI components driven by the canonical Target, ScanRun, Listing, and Evaluation records rather than Google Sheets-shaped dictionaries.

## Acceptance criteria

- The sole user can sign in, manage targets, start exactly one scan, monitor its state, and inspect results without using Google Sheets or a terminal.
- Every visible listing has a thumbnail or accessible fallback, useful deal facts, and a working Carousell link.
- Editing a target does not alter an active scan or rewrite prior evaluations.
- Supabase removes scan-generated data older than three days while targets remain; the frontend shows only the newest completed scan.
- The interface remains clear and operable from a phone-sized viewport through desktop dths.wi
