"""Command-line entry point for the Carousell Deal Finder pipeline."""

from __future__ import annotations

import logging
import sys
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests

from .config import BASE_DIR
from .deal_engine import find_deals
from .scraper import ScraperStructureError, scrape_all_categories
from .sheets_handler import PriceListError, read_price_list_rows
from .sheets_writer import SheetsWriterError, write_outputs


LOG_FILE = Path(BASE_DIR) / "logs" / "deal_finder.log"


def configure_logging(log_file: Path = LOG_FILE) -> None:
    """Configure concise console output plus a persistent local run log."""
    logger = logging.getLogger()
    if logger.handlers:
        return
    log_file.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[logging.StreamHandler(), logging.FileHandler(log_file, encoding="utf-8")],
    )


def _category_from_url(url: str) -> str:
    path = urlparse(url).path.rstrip("/")
    last_segment = path.rsplit("/", maxsplit=1)[-1]
    return last_segment.rsplit("-", maxsplit=1)[0] if "-" in last_segment else last_segment


def flatten_category_results(
    category_results: Mapping[str, Sequence[Mapping[str, Any]]],
) -> list[dict[str, Any]]:
    """Flatten category batches and retain the source category on every listing."""
    listings: list[dict[str, Any]] = []
    for url, category_listings in category_results.items():
        category = _category_from_url(url)
        for listing in category_listings:
            listings.append({**dict(listing), "category": listing.get("category") or category})
    return listings


def run_pipeline(
    *,
    scrape_categories: Callable[[], Mapping[str, Sequence[Mapping[str, Any]]]] = scrape_all_categories,
    read_price_list: Callable[[], Sequence[Mapping[str, Any]]] = read_price_list_rows,
    write_results: Callable[[Sequence[Mapping[str, Any]], Sequence[Mapping[str, Any]]], Mapping[str, int]] = write_outputs,
) -> dict[str, int]:
    """Run scrape → match → write, returning counts suitable for logging or a CLI."""
    category_results = scrape_categories()
    listings = flatten_category_results(category_results)
    reference_rows = read_price_list()
    deals = find_deals(listings, reference_rows)
    write_summary = write_results(deals, listings)
    summary = {"scraped": len(listings), "deals": len(deals), **dict(write_summary)}
    logging.info(
        "Pipeline complete: scraped=%d deals=%d history_appended=%d history_updated=%d",
        summary["scraped"],
        summary["deals"],
        summary.get("history_appended", 0),
        summary.get("history_updated", 0),
    )
    return summary


def main() -> int:
    """Run the pipeline and return a shell-compatible status code."""
    configure_logging()
    try:
        summary = run_pipeline()
    except ScraperStructureError as error:
        logging.error("Scraper structure failure: %s", error)
        print(f"Scrape stopped safely: {error}", file=sys.stderr)
        return 1
    except (requests.RequestException, PriceListError, SheetsWriterError) as error:
        logging.error("Pipeline failure: %s", error)
        print(f"Deal finder failed: {error}", file=sys.stderr)
        return 1
    except Exception:
        logging.exception("Unexpected pipeline failure")
        print("Deal finder failed unexpectedly. See logs\\deal_finder.log for details.", file=sys.stderr)
        return 1

    print(
        f"Done: {summary['scraped']} listings scanned, {summary['deals']} deals found."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
