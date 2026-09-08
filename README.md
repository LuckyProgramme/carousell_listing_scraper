# Carousell Deal Finder

A two-stage Carousell deal finder for Google Sheets. The system retrieves recent Carousell listings, matches them against targets in a Google Sheets `Price List` tab, applies deterministic safety checks, and uses Gemini to audit likely matches before publishing confirmed deals.

## What is included

The final repository contains the application source, prompts, tests, and documentation. It does not contain credentials or local runtime configuration.

Keep these files local and never commit them:

- `.env` — Gemini API key, spreadsheet ID, and local settings.
- `service_account.json` — Google service-account private credentials.
- `logs/` — audit reports and runtime logs.
- exported spreadsheets such as `deal_finder_result.xlsx`.

## Requirements

- Windows, macOS, or Linux
- Python 3.10 or newer
- A Google Cloud service account with Google Sheets API access
- A Gemini API key
- A Google Sheet shared with the service-account email address

Install the runtime dependencies manually when `pyproject.toml` is not included:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install beautifulsoup4 requests gspread rapidfuzz "nicegui>=3.0,<4"
```

Install `pytest` as well if you want to run the test suite:

```powershell
python -m pip install pytest
```

## Local configuration

Copy `.env.example` to `.env` and replace the placeholders:

```powershell
Copy-Item .env.example .env
```

Example configuration:

```env
GEMINI_API_KEY=your_gemini_api_key_here
GEMINI_MODEL=gemini-3.1-flash-lite
GEMINI_AUDIT_CHUNK_SIZE=20
GEMINI_AUDIT_TIMEOUT_SECONDS=30
GEMINI_TIMEOUT_RETRIES=1

SPREADSHEET_ID=your_google_spreadsheet_id_here
SERVICE_ACCOUNT_FILE=service_account.json

REQUEST_DELAY_SECONDS=5
DEFAULT_TIMEOUT_SECONDS=15.0
```

The application loads `.env` automatically. The real Gemini key, service-account JSON, and spreadsheet ID belong only in local files or environment variables.

## Google Sheets setup

1. Create or select a Google Cloud project.
2. Enable the Google Sheets API.
3. Create a service account and download its JSON key locally as `service_account.json`.
4. Copy the service account's `client_email`.
5. Share the target Google Sheet with that email address as an Editor.
6. Put the spreadsheet ID from the Sheet URL into `.env`.

The application reads the `Price List` tab by column name. The current seeded header layout is:

```text
Item Name | Category | Search Mode | Retail Price (PHP) | Deal Price (PHP) | Keyword for Condition Downsizing | Keyword for Finding Freebies | Notes | Target Type | Allow Bundle Check
```

Existing sheets remain compatible:

- Blank or missing `Search Mode` means `Category`.
- `Category` mode requires a recognized category and uses its recent-first Carousell category URL.
- `Item Name` mode searches the exact normalized Item Name and ignores Category for retrieval.
- Blank or missing `Target Type` means `Hardware`; the supported explicit value for game software is `Game`.
- Blank, missing, `FALSE`, `No`, or `0` in `Allow Bundle Check` means false.
- `TRUE`, `Yes`, or `1` enables bundle checking for that target.

Column order may vary because headers are matched by name. Existing populated rows are not rearranged automatically.

## Running the application without `pyproject.toml`

Because the source uses a `src` layout, set `PYTHONPATH` from the project root before running commands:

```powershell
$env:PYTHONPATH = "$PWD\src"
```

Run a read-only audit first:

```powershell
python -m deal_finder.deal_finder --audit
```

`--audit` and `--dry-run` scrape Carousell and call Gemini without writing Google Sheets. They create a local report under `logs/`, including source summaries, Gemini chunk results, fallback comparisons, and validated decisions.

Run the normal publishing pipeline only after reviewing an audit:

```powershell
python -m deal_finder.deal_finder
```

Normal runs write validated results to `Current Deals`, `All Listings`, and `History`. Only Gemini-approved deals are published when Gemini is available. Local fallback decisions remain comparison data in audit mode.

## Web dashboard

Install dependencies and start the local NiceGUI app:

```powershell
uv sync
uv run deal-finder-ui
```

The dashboard opens at `http://127.0.0.1:8080`. Use `--port 8081` to change the port or `--no-browser` to suppress opening a browser. It binds to localhost and is intended for personal use.

Paste a Google Sheets editor URL or raw workbook ID into the connection field. **Validate connection** checks read access without changing permissions or spreadsheet contents. Share the workbook with the displayed service account email as Editor in Google Sheets. Read access alone does not prove Editor access. Published `/d/e/` links are not workbook IDs. `SPREADSHEET_ID` in `.env` also accepts a full editor URL.

The run button starts the existing pipeline in a background thread. Progress shows completed stages; the live log drawer reports source fetches and audit activity. Counters show scanned listings, candidates, and accepted deals. Only one run or Price List operation can execute at a time across browser tabs; a run continues if you disconnect. Results and logs remain in memory until the app stops.

**Audit only** is enabled initially: it produces a local report and does not write Sheets. Turn it off to publish to Current Deals, All Listings, and History. Cards show thumbnails when available, savings against your Deal Price target, condition, seller reviews, likes, meetup location, listing date, and a direct Carousell link. Gemini confidence and local lexical scores have distinct labels. Use the filter to search results; cards are sorted by savings.

In **Price List**, load the catalog, select an item to edit, or choose **Add new item**. **Save item** validates prices and search settings before writing that row. Delete asks for confirmation. Custom columns and surrounding rows retain their values. If the sheet changed since loading, reload before saving; this check detects stale edits but cannot make concurrent Google Sheets edits transactional. **Initialize empty Price List** creates/seeds a missing or empty catalog using the existing defaults.

Metadata extraction reads optional values from `listingCards`, including nested photos/sellers and meetup fields. Missing or malformed metadata stays empty. Unix seconds/milliseconds and ISO timestamps normalize to UTC ISO 8601; timezone-free dates assume UTC, and relative dates are left empty. Output tabs use white bold navy headers (`#1A365D`), green confidence cells (`#1B5E20`), condition colors, and bold PHP currency values. Only generated thumbnail formulas are evaluated; listing text is written as raw values.

Implementation references: [NiceGUI background I/O](https://nicegui.io/documentation/section_action_events), [Google Sheets formatting](https://developers.google.com/workspace/sheets/api/samples/formatting).

## Current matching behavior

- Item Name searches use Carousell's recent-first URL and retain the first 20 results.
- Category searches retain the complete first result page.
- Candidate matching applies model, accessory, target-source, and price gates before Gemini.
- Gemini audits run in sequential chunks of 20 candidates by default, with a 30-second timeout and one timeout retry.
- Gemini responses must pass the target whitelist, confidence, specification, and accessory checks.
- A bundle requires `Allow Bundle Check=TRUE`, a displayed listing price no higher than 3× the target Deal Price, and an explicit current individual asking price with permission to buy separately.
- Bundle totals are never divided or estimated. Bundles do not populate freebies, and other items in the same post do not create additional target deals.
- For accepted split deals, Current Deals and History use the verified individual price. All Listings retains the original listing price.

## Testing

```powershell
$env:PYTHONPATH = "$PWD\src"
python -m pytest -q
```

The optional live Carousell test is disabled unless explicitly enabled:

```powershell
$env:RUN_LIVE_CAROUSELL_TESTS = "1"
python -m pytest -q -m live
```

## Security checklist

Before pushing to GitHub, confirm that these are absent from the commit:

```powershell
git status --short
git diff --cached --name-only
```

Do not force-add `.env`, `service_account.json`, logs, spreadsheet exports, virtual environments, or temporary files. If a credential was ever pushed, rotate it; deleting the file in a later commit does not remove it from Git history.
