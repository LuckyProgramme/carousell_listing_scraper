from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent
BASE_DIR = PACKAGE_DIR.parent.parent
SERVICE_ACCOUNT_FILE = BASE_DIR / "service_account.json"

SPREADSHEET_ID = "1VXMvaPbhgxcMqopLCH8nDhOTDDGQDBEfz5WT-G1JGpI"
PRICE_LIST_TAB="Price List"
CURRENT_DEALS_TAB="Current Deals"
ALL_LISTINGS_TAB = "All Listings"
HISTORY_TAB= "History"

CATEGORY_URL = [
    "https://www.carousell.ph/categories/video-gaming-884/?sort_by=3",
   "https://www.carousell.ph/categories/mobile-phones-gadgets-840/?sort_by=3",
   "https://www.carousell.ph/categories/computers-tech-838/?sort_by=3"
]

HEADERS={
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
}

REQUEST_DELAY_SECONDS=5
