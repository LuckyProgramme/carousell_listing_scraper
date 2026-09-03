"""Write deal-finder results to the Google Sheets output tabs."""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from datetime import date
from typing import Any

import gspread
from gspread.exceptions import WorksheetNotFound

from .config import ALL_LISTINGS_TAB, CURRENT_DEALS_TAB, HISTORY_TAB
from .sheets_handler import open_deal_finder_spreadsheet

CURRENT_DEALS_HEADERS = (
    "Item Name",
    "Listing Title",
    "Carousell Price",
    "Deal Price",
    "Savings",
    "Final Condition",
    "Bundles",
    "Category",
    "Link",
    "Seller",
    "Match Score",
)
ALL_LISTINGS_HEADERS = (
    "Listing ID",
    "Listing Title",
    "Carousell Price",
    "Original Condition",
    "Description",
    "Seller",
    "Category",
    "Link",
)
HISTORY_HEADERS = (
    "Listing ID",
    "Item Name",
    "Listing Title",
    "Carousell Price",
    "Deal Price",
    "Savings",
    "Final Condition",
    "Bundles",
    "Category",
    "Link",
    "First Seen Date",
    "Last Seen Date",
)


class SheetsWriterError(RuntimeError):
    """Raised when an output tab cannot be safely updated."""


def get_listing_id(listing: Mapping[str, Any]) -> str:
    """Read a stable listing ID, preferring scraper data and then the URL suffix."""
    listing_id = str(listing.get("id", "")).strip()
    if listing_id:
        return listing_id
    link = str(listing.get("link", "")).strip()
    match = re.search(r"-(\d+)/?$", link)
    return match.group(1) if match else link


def _bundles_value(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, Iterable):
        return ", ".join(str(item) for item in value)
    return ""


def _get_or_create_worksheet(
    spreadsheet: gspread.Spreadsheet,
    title: str,
    column_count: int,
) -> gspread.Worksheet:
    try:
        return spreadsheet.worksheet(title)
    except WorksheetNotFound:
        return spreadsheet.add_worksheet(
            title=title, rows="100", cols=str(column_count)
        )


def _overwrite_tab(
    worksheet: gspread.Worksheet,
    headers: Sequence[str],
    rows: Sequence[Sequence[Any]],
) -> None:
    worksheet.clear()
    worksheet.update(
        range_name="A1", values=[list(headers), *[list(row) for row in rows]]
    )


def _current_deal_row(deal: Mapping[str, Any]) -> list[Any]:
    return [
        deal.get("matched_item", ""),
        deal.get("title", ""),
        deal.get("price", ""),
        deal.get("deal_price", ""),
        deal.get("savings", ""),
        deal.get("final_condition", deal.get("condition", "")),
        _bundles_value(deal.get("bundles", "")),
        deal.get("reference_category", deal.get("category", "")),
        deal.get("link", ""),
        deal.get("seller", ""),
        deal.get("match_score", ""),
    ]


def _all_listing_row(listing: Mapping[str, Any]) -> list[Any]:
    return [
        get_listing_id(listing),
        listing.get("title", ""),
        listing.get("price", ""),
        listing.get("condition", ""),
        listing.get("description", ""),
        listing.get("seller", ""),
        listing.get("category", ""),
        listing.get("link", ""),
    ]


def _history_row(deal: Mapping[str, Any], seen_date: str) -> list[Any]:
    return [
        get_listing_id(deal),
        deal.get("matched_item", ""),
        deal.get("title", ""),
        deal.get("price", ""),
        deal.get("deal_price", ""),
        deal.get("savings", ""),
        deal.get("final_condition", deal.get("condition", "")),
        _bundles_value(deal.get("bundles", "")),
        deal.get("reference_category", deal.get("category", "")),
        deal.get("link", ""),
        seen_date,
        seen_date,
    ]


def write_history(
    deals: Iterable[Mapping[str, Any]],
    spreadsheet: gspread.Spreadsheet,
    *,
    seen_date: str | None = None,
) -> tuple[int, int]:
    """Append new deals and update ``Last Seen Date`` for known listing IDs."""
    worksheet = _get_or_create_worksheet(spreadsheet, HISTORY_TAB, len(HISTORY_HEADERS))
    existing_values = worksheet.get_all_values()
    if not existing_values or not any(
        str(cell).strip() for row in existing_values for cell in row
    ):
        worksheet.update(range_name="A1", values=[list(HISTORY_HEADERS)])
        existing_values = [list(HISTORY_HEADERS)]
    if tuple(existing_values[0]) != HISTORY_HEADERS:
        raise SheetsWriterError(f"'{HISTORY_TAB}' has an unexpected header row.")

    id_column = HISTORY_HEADERS.index("Listing ID")
    last_seen_column = HISTORY_HEADERS.index("Last Seen Date")
    existing_by_id = {
        row[id_column]: row_index
        for row_index, row in enumerate(existing_values[1:], start=2)
        if len(row) > id_column and row[id_column]
    }
    seen_date = seen_date or date.today().isoformat()
    appended = updated = 0
    processed_ids: set[str] = set()
    new_rows: list[list[Any]] = []
    for deal in deals:
        listing_id = get_listing_id(deal)
        if not listing_id or listing_id in processed_ids:
            continue
        processed_ids.add(listing_id)
        if listing_id in existing_by_id:
            worksheet.update_cell(
                existing_by_id[listing_id], last_seen_column + 1, seen_date
            )
            updated += 1
        else:
            new_rows.append(_history_row(deal, seen_date))
            appended += 1
    if new_rows:
        worksheet.append_rows(new_rows)
    return appended, updated


def write_outputs(
    deals: Iterable[Mapping[str, Any]],
    all_listings: Iterable[Mapping[str, Any]],
    spreadsheet: gspread.Spreadsheet | None = None,
    *,
    seen_date: str | None = None,
) -> dict[str, int]:
    """Overwrite current tabs and maintain append-only, deduplicated History."""
    spreadsheet = spreadsheet or open_deal_finder_spreadsheet()
    deal_rows = list(deals)
    listing_rows = list(all_listings)

    current_deals = _get_or_create_worksheet(
        spreadsheet, CURRENT_DEALS_TAB, len(CURRENT_DEALS_HEADERS)
    )
    all_listings_tab = _get_or_create_worksheet(
        spreadsheet, ALL_LISTINGS_TAB, len(ALL_LISTINGS_HEADERS)
    )
    _overwrite_tab(
        current_deals,
        CURRENT_DEALS_HEADERS,
        [_current_deal_row(deal) for deal in deal_rows],
    )
    _overwrite_tab(
        all_listings_tab,
        ALL_LISTINGS_HEADERS,
        [_all_listing_row(listing) for listing in listing_rows],
    )
    history_appended, history_updated = write_history(
        deal_rows, spreadsheet, seen_date=seen_date
    )
    return {
        "current_deals": len(deal_rows),
        "all_listings": len(listing_rows),
        "history_appended": history_appended,
        "history_updated": history_updated,
    }
