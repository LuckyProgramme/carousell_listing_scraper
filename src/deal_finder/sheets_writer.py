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
    "Freebies",
    "Issues / Defects",
    "Audit Source",
    "Confidence / Score",
    "Specs Matched",
    "Seller",
    "Seller Rating",
    "Likes",
    "Location",
    "Listing Date",
    "Thumbnail",
    "Category",
    "Link",
)
ALL_LISTINGS_HEADERS = (
    "Listing ID",
    "Thumbnail",
    "Listing Title",
    "Carousell Price",
    "Price Status",
    "Original Condition",
    "Seller",
    "Seller Rating",
    "Likes",
    "Location",
    "Listing Date",
    "Category",
    "Description",
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
    "Freebies",
    "Issues / Defects",
    "Audit Source",
    "Confidence / Score",
    "Seller",
    "Seller Rating",
    "Category",
    "Link",
    "First Seen Date",
    "Last Seen Date",
)
LEGACY_HISTORY_HEADERS = (
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


def _column_letter(column_number: int) -> str:
    """Convert a one-indexed column number to A1 notation."""
    result = ""
    while column_number:
        column_number, remainder = divmod(column_number - 1, 26)
        result = chr(ord("A") + remainder) + result
    return result


def _format_freebies(deal: Mapping[str, Any]) -> str:
    raw = deal.get("freebies") or deal.get("bundles", "")
    if isinstance(raw, str):
        return raw
    if isinstance(raw, Iterable):
        return ", ".join(str(item).strip() for item in raw if str(item).strip())
    return ""


def _format_issues(deal: Mapping[str, Any]) -> str:
    raw = deal.get("issues", "")
    if isinstance(raw, str):
        return raw
    if isinstance(raw, Iterable):
        return ", ".join(str(item).strip() for item in raw if str(item).strip())
    return ""


def _format_audit_source(deal: Mapping[str, Any]) -> str:
    source = str(deal.get("audit_source", "")).strip()
    if source == "gemini":
        return "Gemini"
    if source == "local_fallback":
        return "Local Fallback"
    return source.title() if source else "Local Fallback"


def _format_score(deal: Mapping[str, Any]) -> str:
    if deal.get("gemini_confidence") is not None:
        return f"{deal['gemini_confidence']}%"
    if deal.get("local_match_score") is not None:
        return f"{float(deal['local_match_score']):.1f}%"
    raw_match = deal.get("match_score")
    if raw_match is not None and str(raw_match).strip():
        if isinstance(raw_match, (int, float)):
            return f"{float(raw_match):.1f}%"
        return str(raw_match).strip()
    return ""


def _format_specs_matched(deal: Mapping[str, Any]) -> str:
    val = deal.get("specs_matched")
    if val is True:
        return "Yes"
    if val is False:
        return "No"
    return "N/A"


def _format_seller_rating(item: Mapping[str, Any]) -> str:
    rating = item.get("seller_rating")
    count = item.get("seller_rating_count")
    if rating is not None and str(rating).strip() != "":
        try:
            r_val = float(rating)
            if count is not None and str(count).strip() != "":
                return f"{r_val:.1f} ({int(count)})"
            return f"{r_val:.1f}"
        except (ValueError, TypeError):
            return str(rating)
    return ""


def _format_thumbnail(item: Mapping[str, Any]) -> str:
    url = str(item.get("thumbnail_url") or "").strip()
    if url.startswith("http://") or url.startswith("https://"):
        return f'=IMAGE("{url}")'
    return ""


def _format_price_status(item: Mapping[str, Any]) -> str:
    flag = str(item.get("price_flag") or item.get("price_status") or "").strip()
    if not flag or flag.lower() == "normal":
        return "Normal"
    if "recovered" in flag.lower():
        return "Recovered (Text)"
    if "zero" in flag.lower() or "placeholder" in flag.lower():
        return "Placeholder Zero"
    if "low" in flag.lower() or "suspicious" in flag.lower():
        return "Suspicious Low"
    return flag.title()


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
        deal.get("carousell_price", deal.get("price", "")),
        deal.get("deal_price", ""),
        deal.get("savings", ""),
        deal.get("final_condition", deal.get("condition", "")),
        _format_freebies(deal),
        _format_issues(deal),
        _format_audit_source(deal),
        _format_score(deal),
        _format_specs_matched(deal),
        deal.get("seller", ""),
        _format_seller_rating(deal),
        deal.get("like_count", ""),
        deal.get("location", ""),
        deal.get("listing_timestamp", ""),
        _format_thumbnail(deal),
        deal.get("category", deal.get("reference_category", "")),
        deal.get("link", ""),
    ]


def _all_listing_row(listing: Mapping[str, Any]) -> list[Any]:
    return [
        get_listing_id(listing),
        _format_thumbnail(listing),
        listing.get("title", ""),
        listing.get("price", ""),
        _format_price_status(listing),
        listing.get("condition", listing.get("original_condition", "")),
        listing.get("seller", ""),
        _format_seller_rating(listing),
        listing.get("like_count", ""),
        listing.get("location", ""),
        listing.get("listing_timestamp", ""),
        listing.get("category", ""),
        listing.get("description", ""),
        listing.get("link", ""),
    ]


def _history_row(deal: Mapping[str, Any], seen_date: str) -> list[Any]:
    return [
        get_listing_id(deal),
        deal.get("matched_item", ""),
        deal.get("title", ""),
        deal.get("carousell_price", deal.get("price", "")),
        deal.get("deal_price", ""),
        deal.get("savings", ""),
        deal.get("final_condition", deal.get("condition", "")),
        _format_freebies(deal),
        _format_issues(deal),
        _format_audit_source(deal),
        _format_score(deal),
        deal.get("seller", ""),
        _format_seller_rating(deal),
        deal.get("category", deal.get("reference_category", "")),
        deal.get("link", ""),
        seen_date,
        seen_date,
    ]


def _legacy_history_row(deal: Mapping[str, Any], seen_date: str) -> list[Any]:
    return [
        get_listing_id(deal),
        deal.get("matched_item", ""),
        deal.get("title", ""),
        deal.get("carousell_price", deal.get("price", "")),
        deal.get("deal_price", ""),
        deal.get("savings", ""),
        deal.get("final_condition", deal.get("condition", "")),
        _format_freebies(deal),
        deal.get("category", deal.get("reference_category", "")),
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
    header_row = tuple(str(cell).strip() for cell in existing_values[0])
    is_legacy = header_row == LEGACY_HISTORY_HEADERS
    if not is_legacy and header_row != HISTORY_HEADERS:
        if "Listing ID" not in header_row or "Last Seen Date" not in header_row:
            raise SheetsWriterError(f"'{HISTORY_TAB}' has an unexpected header row.")

    id_column = header_row.index("Listing ID")
    last_seen_column = header_row.index("Last Seen Date")
    existing_by_id = {
        row[id_column]: row_index
        for row_index, row in enumerate(existing_values[1:], start=2)
        if len(row) > id_column and row[id_column]
    }
    seen_date = seen_date or date.today().isoformat()
    appended = updated = 0
    processed_ids: set[str] = set()
    new_rows: list[list[Any]] = []
    last_seen_updates: list[dict[str, Any]] = []
    row_builder = _legacy_history_row if is_legacy else _history_row
    for deal in deals:
        listing_id = get_listing_id(deal)
        if not listing_id or listing_id in processed_ids:
            continue
        processed_ids.add(listing_id)
        if listing_id in existing_by_id:
            last_seen_updates.append(
                {
                    "range": f"{_column_letter(last_seen_column + 1)}{existing_by_id[listing_id]}",
                    "values": [[seen_date]],
                }
            )
            updated += 1
        else:
            new_rows.append(row_builder(deal, seen_date))
            appended += 1
    if last_seen_updates:
        worksheet.batch_update(last_seen_updates)
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
