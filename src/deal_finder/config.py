import os
from pathlib import Path
from typing import Final

PACKAGE_DIR: Final[Path] = Path(__file__).resolve().parent
BASE_DIR: Final[Path] = PACKAGE_DIR.parent.parent


def load_env_file(env_path: Path | None = None, override: bool = False) -> dict[str, str]:
    """Lightweight native parser for local .env files into os.environ without dependencies."""
    path = env_path or (BASE_DIR / ".env")
    loaded: dict[str, str] = {}
    if not path.exists() or not path.is_file():
        return loaded

    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" not in line:
                    continue
                key, val = line.split("=", maxsplit=1)
                key = key.strip()
                val = val.strip().strip("'\"")
                if key:
                    loaded[key] = val
                    if override or key not in os.environ:
                        os.environ[key] = val
    except Exception:
        pass
    return loaded


# Automatically load .env on module import if present
load_env_file()


def check_credential_security(
    service_account_path: Path | str | None = None,
) -> list[str]:
    """Inspect local credential security and return diagnostic warnings."""
    warnings: list[str] = []
    sa_path = Path(service_account_path or SERVICE_ACCOUNT_FILE)
    if sa_path.exists():
        try:
            if sa_path.stat().st_size == 0:
                warnings.append(f"Service account file '{sa_path}' is empty.")
        except OSError as exc:
            warnings.append(f"Cannot stat service account file '{sa_path}': {exc}")
    return warnings


# Secrets and sensitive paths (read from environment first)
GEMINI_API_KEY: Final[str] = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL: Final[str] = os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite")
GEMINI_AUDIT_CHUNK_SIZE: Final[int] = int(os.getenv("GEMINI_AUDIT_CHUNK_SIZE", "20"))
GEMINI_AUDIT_TIMEOUT_SECONDS: Final[float] = float(
    os.getenv("GEMINI_AUDIT_TIMEOUT_SECONDS", "30")
)
GEMINI_TIMEOUT_RETRIES: Final[int] = int(os.getenv("GEMINI_TIMEOUT_RETRIES", "1"))
SERVICE_ACCOUNT_FILE: Final[Path] = Path(
    os.getenv("SERVICE_ACCOUNT_FILE", str(BASE_DIR / "service_account.json"))
)
SPREADSHEET_ID: Final[str] = os.getenv(
    "SPREADSHEET_ID", "1VXMvaPbhgxcMqopLCH8nDhOTDDGQDBEfz5WT-G1JGpI"
)

PRICE_LIST_TAB: Final[str] = "Price List"
CURRENT_DEALS_TAB: Final[str] = "Current Deals"
ALL_LISTINGS_TAB: Final[str] = "All Listings"
HISTORY_TAB: Final[str] = "History"

CATEGORY_URLS_BY_NAME: Final[dict[str, str]] = {
    "Video Gaming": "https://www.carousell.ph/categories/video-gaming-884/?sort_by=3",
    "Mobile Phones": "https://www.carousell.ph/categories/mobile-phones-gadgets-840/?sort_by=3",
    "Computers & Tech": "https://www.carousell.ph/categories/computers-tech-838/?sort_by=3",
}

# Backwards-compatible list for callers that still use the category-only scraper.
CATEGORY_URL: Final[list[str]] = list(CATEGORY_URLS_BY_NAME.values())

HEADERS: Final[dict[str, str]] = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
}

REQUEST_DELAY_SECONDS: Final[float] = float(os.getenv("REQUEST_DELAY_SECONDS", "5"))
DEFAULT_TIMEOUT_SECONDS: Final[float] = float(os.getenv("DEFAULT_TIMEOUT_SECONDS", "15.0"))
