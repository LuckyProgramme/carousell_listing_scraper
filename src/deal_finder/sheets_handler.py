"""Google Sheets input/output helpers for the Carousell deal finder."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

import gspread
from gspread.exceptions import WorksheetNotFound

from .config import PRICE_LIST_TAB, SERVICE_ACCOUNT_FILE, SPREADSHEET_ID

PRICE_LIST_HEADERS = (
    "Item Name",
    "Category",
    "Retail Price (PHP)",
    "Deal Price (PHP)",
    "Keyword for Condition Downsizing",
    "Keyword for Finding Freebies",
    "Notes",
)

# The initial catalog from the implementation plan. It is written only to a
# missing or empty Price List tab; existing user-maintained rows are untouched.
DEFAULT_PRICE_LIST_ROWS = (
    (
        "PS5 Slim",
        "Video Gaming",
        30000,
        18000,
        "issue, defect, replaced",
        "comes with, free, includes",
        "Target disc version",
    ),
    (
        "PS5 Slim Digital",
        "Video Gaming",
        26000,
        16000,
        "issue, defect, replaced",
        "comes with, free, includes",
        "Digital only",
    ),
    (
        "Nintendo Switch OLED",
        "Video Gaming",
        16000,
        10000,
        "drift, scratch, repair",
        "free, includes, bundle",
        "",
    ),
    (
        "iPhone 15",
        "Mobile Phones",
        45000,
        28000,
        "bypass, issue, scratch",
        "case, charger, free",
        "",
    ),
    (
        "iPhone 15 Pro Max",
        "Mobile Phones",
        70000,
        45000,
        "bypass, crack, issue",
        "case, free, bundle",
        "",
    ),
    (
        "iPad Air 5",
        "Computers & Tech",
        35000,
        22000,
        "crack, dent, issue",
        "pencil, folio, free",
        "",
    ),
    (
        "M1 MacBook Air",
        "Computers & Tech",
        42000,
        25000,
        "battery, issue, dent",
        "charger, bag, free",
        "8GB/256GB base",
    ),
    (
        "Sony WH-1000XM5",
        "Computers & Tech",
        18000,
        10000,
        "pad, issue, replaced",
        "case, cable, free",
        "",
    ),
)


class PriceListError(RuntimeError):
    """Raised when the Price List tab cannot safely be read."""


def open_deal_finder_spreadsheet() -> gspread.Spreadsheet:
    """Authenticate with the service account and open the configured workbook."""
    client = gspread.service_account(filename=str(SERVICE_ACCOUNT_FILE))
    return client.open_by_key(SPREADSHEET_ID)


def _normalise_headers(headers: Sequence[str]) -> list[str]:
    return [str(header).strip() for header in headers]


def _validate_headers(headers: Sequence[str]) -> None:
    missing = [header for header in PRICE_LIST_HEADERS if header not in headers]
    if missing:
        raise PriceListError(
            f"'{PRICE_LIST_TAB}' is missing required columns: {', '.join(missing)}"
        )


def _find_header_row(values: Sequence[Sequence[str]]) -> tuple[int, list[str]] | None:
    for index, row in enumerate(values):
        headers = _normalise_headers(row)
        if all(header in headers for header in PRICE_LIST_HEADERS):
            return index, headers
    return None


def _column_letter(column_number: int) -> str:
    result = ""
    while column_number:
        column_number, remainder = divmod(column_number - 1, 26)
        result = chr(ord("A") + remainder) + result
    return result


def ensure_price_list_tab(
    spreadsheet: gspread.Spreadsheet | None = None,
) -> gspread.Worksheet:
    """Return a populated Price List tab without overwriting existing data."""
    spreadsheet = spreadsheet or open_deal_finder_spreadsheet()
    try:
        worksheet = spreadsheet.worksheet(PRICE_LIST_TAB)
    except WorksheetNotFound:
        worksheet = spreadsheet.add_worksheet(
            title=PRICE_LIST_TAB,
            rows=str(len(DEFAULT_PRICE_LIST_ROWS) + 1),
            cols=str(len(PRICE_LIST_HEADERS)),
        )

    values = worksheet.get_all_values()
    if not values or not any(cell.strip() for row in values for cell in row):
        worksheet.update(
            range_name="A1",
            values=[
                list(PRICE_LIST_HEADERS),
                *[list(row) for row in DEFAULT_PRICE_LIST_ROWS],
            ],
        )
        return worksheet

    header_row = _find_header_row(values)
    if header_row is None:
        raise PriceListError(
            f"Could not find the required header row in '{PRICE_LIST_TAB}'."
        )
    header_index, headers = header_row
    _validate_headers(headers)
    item_name_column = headers.index("Item Name")
    has_items = any(
        len(row) > item_name_column and row[item_name_column].strip()
        for row in values[header_index + 1 :]
    )
    if not has_items:
        start_column = _column_letter(item_name_column + 1)
        worksheet.update(
            range_name=f"{start_column}{header_index + 2}",
            values=[list(row) for row in DEFAULT_PRICE_LIST_ROWS],
        )
    return worksheet


def _parse_price(value: str) -> float | None:
    text = str(value).replace(",", "")
    match = re.search(r"-?\d+(?:\.\d+)?", text)
    return float(match.group()) if match else None


def read_price_list_rows(
    spreadsheet: gspread.Spreadsheet | None = None,
) -> list[dict[str, str | float | None]]:
    """Fetch normalized records from the configured ``Price List`` worksheet."""
    worksheet = ensure_price_list_tab(spreadsheet)
    values = worksheet.get_all_values()
    if not values:
        raise PriceListError(f"'{PRICE_LIST_TAB}' could not be initialized.")

    header_row = _find_header_row(values)
    if header_row is None:
        raise PriceListError(
            f"Could not find the required header row in '{PRICE_LIST_TAB}'."
        )
    header_index, headers = header_row
    _validate_headers(headers)
    rows: list[dict[str, str | float | None]] = []
    for values_row in values[header_index + 1 :]:
        padded_row = [*values_row, *[""] * (len(headers) - len(values_row))]
        record = {
            header: padded_row[index]
            for index, header in enumerate(headers)
            if header in PRICE_LIST_HEADERS
        }
        if not str(record["Item Name"]).strip():
            continue
        for price_header in ("Retail Price (PHP)", "Deal Price (PHP)"):
            record[price_header] = _parse_price(str(record[price_header]))
        rows.append(record)
    return rows
