"""Google Sheets input/output helpers for the Carousell deal finder."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import gspread
from gspread.exceptions import WorksheetNotFound
from gspread.utils import ValidationConditionType

from .config import PRICE_LIST_TAB, SERVICE_ACCOUNT_FILE, SPREADSHEET_ID
from .models import parse_bundle_check, parse_target_type

# Principle of Least Privilege:
# spreadsheets scope + restricted drive.file scope (avoids full drive access)
DEFAULT_SCOPES = (
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.file",
)

PRICE_LIST_HEADERS = (
    "Item Name",
    "Category",
    "Search Mode",
    "Retail Price (PHP)",
    "Deal Price (PHP)",
    "Keyword for Condition Downsizing",
    "Keyword for Finding Freebies",
    "Notes",
    "Target Type",
    "Allow Bundle Check",
)
REQUIRED_PRICE_LIST_HEADERS = tuple(
    header for header in PRICE_LIST_HEADERS
    if header not in {"Search Mode", "Target Type", "Allow Bundle Check"}
)

# The initial catalog from the implementation plan. It is written only to a
# missing or empty Price List tab; existing user-maintained rows are untouched.
DEFAULT_PRICE_LIST_ROWS = (
    (
        "PS5 Slim",
        "Video Gaming",
        "Category",
        30000,
        18000,
        "issue, defect, replaced",
        "comes with, free, includes",
        "Target disc version",
    ),
    (
        "PS5 Slim Digital",
        "Video Gaming",
        "Category",
        26000,
        16000,
        "issue, defect, replaced",
        "comes with, free, includes",
        "Digital only",
    ),
    (
        "Nintendo Switch OLED",
        "Video Gaming",
        "Category",
        16000,
        10000,
        "drift, scratch, repair",
        "free, includes, bundle",
        "",
    ),
    (
        "iPhone 15",
        "Mobile Phones",
        "Category",
        45000,
        28000,
        "bypass, issue, scratch",
        "case, charger, free",
        "",
    ),
    (
        "iPhone 15 Pro Max",
        "Mobile Phones",
        "Category",
        70000,
        45000,
        "bypass, crack, issue",
        "case, free, bundle",
        "",
    ),
    (
        "iPad Air 5",
        "Computers & Tech",
        "Category",
        35000,
        22000,
        "crack, dent, issue",
        "pencil, folio, free",
        "",
    ),
    (
        "M1 MacBook Air",
        "Computers & Tech",
        "Category",
        42000,
        25000,
        "battery, issue, dent",
        "charger, bag, free",
        "8GB/256GB base",
    ),
    (
        "Sony WH-1000XM5",
        "Computers & Tech",
        "Category",
        18000,
        10000,
        "pad, issue, replaced",
        "case, cable, free",
        "",
    ),
)


DEFAULT_PRICE_LIST_ROWS = tuple((*row, "Hardware", False) for row in DEFAULT_PRICE_LIST_ROWS)


class PriceListError(RuntimeError):
    """Raised when the Price List tab cannot safely be read."""


class SheetPermissionError(RuntimeError):
    """Raised when the service account has insufficient permissions or cannot open the spreadsheet."""


def get_service_account_email(service_account_file: Path | str | None = None) -> str | None:
    """Read client_email from the service account JSON file without network requests."""
    sa_path = Path(service_account_file or SERVICE_ACCOUNT_FILE)
    if not sa_path.exists():
        return None
    try:
        with open(sa_path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        return data.get("client_email")
    except Exception:
        return None


def open_deal_finder_spreadsheet(
    spreadsheet_id: str | None = None,
    service_account_file: Path | str | None = None,
    scopes: Sequence[str] = DEFAULT_SCOPES,
) -> gspread.Spreadsheet:
    """Authenticate with the service account using restricted scopes and open the configured workbook.

    Reports clear, actionable diagnostics on permission and connection failures.
    """
    sa_path = Path(service_account_file or SERVICE_ACCOUNT_FILE)
    target_id = spreadsheet_id or SPREADSHEET_ID
    sa_email = get_service_account_email(sa_path) or "unknown service account"

    if not sa_path.exists():
        raise SheetPermissionError(
            f"Service account file not found at '{sa_path}'. "
            f"Please place your Google Cloud service account JSON file there and configure SERVICE_ACCOUNT_FILE."
        )

    try:
        client = gspread.service_account(filename=str(sa_path), scopes=list(scopes))
    except Exception as exc:
        raise SheetPermissionError(
            f"Failed to authenticate service account using '{sa_path}': {exc}"
        ) from exc

    try:
        return client.open_by_key(target_id)
    except gspread.exceptions.SpreadsheetNotFound as exc:
        raise SheetPermissionError(
            f"Spreadsheet '{target_id}' not found or service account has no access. "
            f"Please share the Google Sheet with '{sa_email}' as 'Editor'."
        ) from exc
    except gspread.exceptions.APIError as exc:
        code = getattr(exc.response, "status_code", None) if hasattr(exc, "response") else None
        if code in (403, 404):
            raise SheetPermissionError(
                f"Access denied (HTTP {code}) to spreadsheet '{target_id}'. "
                f"Please open Google Sheets -> Share -> add '{sa_email}' as 'Editor'."
            ) from exc
        raise


@dataclass(frozen=True)
class PermissionValidationResult:
    """Structured result of a non-destructive spreadsheet permission check."""

    valid: bool
    can_read: bool
    can_write: bool
    service_account_email: str | None
    spreadsheet_id: str
    spreadsheet_title: str | None = None
    error_message: str | None = None
    diagnostic_guidance: str | None = None


def validate_sheet_permissions(
    spreadsheet_id: str | None = None,
    service_account_file: Path | str | None = None,
) -> PermissionValidationResult:
    """Validate spreadsheet connectivity and permissions non-destructively.

    SAFETY GUARANTEE:
    Defaults to validation only. Does NOT modify sheet permissions, does NOT
    grant external access, and performs zero external mutations.
    """
    target_id = spreadsheet_id or SPREADSHEET_ID
    sa_path = Path(service_account_file or SERVICE_ACCOUNT_FILE)
    sa_email = get_service_account_email(sa_path)

    if not sa_path.exists():
        return PermissionValidationResult(
            valid=False,
            can_read=False,
            can_write=False,
            service_account_email=None,
            spreadsheet_id=target_id,
            error_message=f"Service account file missing: {sa_path}",
            diagnostic_guidance="Place service_account.json in the project root or configure SERVICE_ACCOUNT_FILE in .env.",
        )

    try:
        spreadsheet = open_deal_finder_spreadsheet(
            spreadsheet_id=target_id, service_account_file=sa_path
        )
        title = spreadsheet.title
        worksheet = spreadsheet.sheet1
        _ = worksheet.title
        can_read = True
    except SheetPermissionError as exc:
        return PermissionValidationResult(
            valid=False,
            can_read=False,
            can_write=False,
            service_account_email=sa_email,
            spreadsheet_id=target_id,
            error_message=str(exc),
            diagnostic_guidance=f"Share Google Sheet '{target_id}' with '{sa_email or 'service account'}' as 'Editor'.",
        )
    except Exception as exc:
        return PermissionValidationResult(
            valid=False,
            can_read=False,
            can_write=False,
            service_account_email=sa_email,
            spreadsheet_id=target_id,
            error_message=str(exc),
            diagnostic_guidance="Verify your network connection and Google Sheets API status.",
        )

    return PermissionValidationResult(
        valid=True,
        can_read=can_read,
        can_write=True,
        service_account_email=sa_email,
        spreadsheet_id=target_id,
        spreadsheet_title=title,
        error_message=None,
        diagnostic_guidance=None,
    )


def share_spreadsheet_explicit(
    email: str,
    role: str = "editor",
    spreadsheet: gspread.Spreadsheet | None = None,
    *,
    service_account_file: Path | str | None = None,
) -> dict[str, Any]:
    """Explicit user-initiated sharing of the spreadsheet with a user email.

    SAFETY BOUNDARY:
    - Requires an explicit user request (CLI or UI confirmation).
    - Never called automatically or during pipeline runs.
    - Validates email format.
    - Reports Drive API permission errors clearly (e.g., if Service Account
      is an Editor and not Owner, Google Drive forbids creating permissions).
    """
    clean_email = str(email or "").strip()
    if "@" not in clean_email or "." not in clean_email:
        raise ValueError(f"Invalid email address provided: '{clean_email}'")

    spreadsheet = spreadsheet or open_deal_finder_spreadsheet(
        service_account_file=service_account_file
    )
    sa_email = get_service_account_email(service_account_file)

    try:
        result = spreadsheet.share(clean_email, perm_type="user", role=role)
        return {
            "success": True,
            "email": clean_email,
            "role": role,
            "spreadsheet_id": spreadsheet.id,
            "details": result,
        }
    except gspread.exceptions.APIError as exc:
        try:
            error_detail = str(exc)
        except Exception:
            error_detail = getattr(getattr(exc, "response", None), "text", "API Error")
        guidance = (
            f"Failed to share spreadsheet with '{clean_email}'. "
            f"Google Drive returned: {error_detail}. "
            f"Note: If the service account '{sa_email}' is an Editor and not the Owner, "
            f"Google Drive prevents it from sharing with other users. "
            f"Please share the sheet directly from the Google Sheets UI."
        )
        raise SheetPermissionError(guidance) from exc
    except Exception as exc:
        raise SheetPermissionError(f"Unexpected error while sharing spreadsheet: {exc}") from exc


def _normalise_headers(headers: Sequence[str]) -> list[str]:
    return [str(header).strip() for header in headers]


def _validate_headers(headers: Sequence[str]) -> None:
    missing = [header for header in REQUIRED_PRICE_LIST_HEADERS if header not in headers]
    if missing:
        raise PriceListError(
            f"'{PRICE_LIST_TAB}' is missing required columns: {', '.join(missing)}"
        )


def _find_header_row(values: Sequence[Sequence[str]]) -> tuple[int, list[str]] | None:
    for index, row in enumerate(values):
        headers = _normalise_headers(row)
        if all(header in headers for header in REQUIRED_PRICE_LIST_HEADERS):
            return index, headers
    return None


def _column_letter(column_number: int) -> str:
    result = ""
    while column_number:
        column_number, remainder = divmod(column_number - 1, 26)
        result = chr(ord("A") + remainder) + result
    return result


def _seed_rows_for_headers(headers: Sequence[str], start_index: int) -> list[list[Any]]:
    """Align default records to an existing header layout without moving columns."""
    default_records = [dict(zip(PRICE_LIST_HEADERS, row)) for row in DEFAULT_PRICE_LIST_ROWS]
    return [
        [record.get(header, "") for header in headers[start_index:]]
        for record in default_records
    ]


def _setup_bundle_checkboxes(worksheet: gspread.Worksheet, headers: Sequence[str], header_index: int) -> None:
    """Set native checkboxes during empty-tab setup; populated tabs are left intact."""
    if "Allow Bundle Check" in headers:
        column = _column_letter(headers.index("Allow Bundle Check") + 1)
        worksheet.add_validation(
            f"{column}{header_index + 2}:{column}",
            ValidationConditionType.boolean,
            [],
            strict=False,  # Text Yes/No and 1/0 remain accepted by the reader.
            showCustomUi=True,
        )


def ensure_price_list_tab(
    spreadsheet: gspread.Spreadsheet | None = None,
    *,
    return_values: bool = False,
) -> gspread.Worksheet | tuple[gspread.Worksheet, list[list[str]]]:
    """Return a populated Price List tab and optionally reuse its fetched values."""
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
        values = [list(PRICE_LIST_HEADERS), *[list(row) for row in DEFAULT_PRICE_LIST_ROWS]]
        worksheet.update(range_name="A1", values=values)
        _setup_bundle_checkboxes(worksheet, PRICE_LIST_HEADERS, 0)
        return (worksheet, values) if return_values else worksheet

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
        _setup_bundle_checkboxes(worksheet, headers, header_index)
        start_column = _column_letter(item_name_column + 1)
        seed_rows = _seed_rows_for_headers(headers, item_name_column)
        worksheet.update(
            range_name=f"{start_column}{header_index + 2}",
            values=seed_rows,
        )
        normalized_values = [list(row) for row in values]
        required_rows = header_index + 1 + len(DEFAULT_PRICE_LIST_ROWS)
        while len(normalized_values) < required_rows:
            normalized_values.append([])
        for offset, default_row in enumerate(seed_rows, start=header_index + 1):
            row = normalized_values[offset]
            required_columns = item_name_column + len(default_row)
            row.extend([""] * max(0, required_columns - len(row)))
            row[item_name_column:required_columns] = list(default_row)
        values = normalized_values
    return (worksheet, values) if return_values else worksheet


def _parse_price(value: str) -> float | None:
    text = str(value).replace(",", "")
    match = re.search(r"-?\d+(?:\.\d+)?", text)
    return float(match.group()) if match else None


def read_price_list_rows(
    spreadsheet: gspread.Spreadsheet | None = None,
    *,
    initialize: bool = True,
) -> list[dict[str, str | float | None]]:
    """Fetch normalized records from the configured ``Price List`` worksheet."""
    if initialize:
        worksheet, values = ensure_price_list_tab(spreadsheet, return_values=True)
    else:
        spreadsheet = spreadsheet or open_deal_finder_spreadsheet()
        try:
            worksheet = spreadsheet.worksheet(PRICE_LIST_TAB)
        except WorksheetNotFound as exc:
            raise PriceListError(
                f"'{PRICE_LIST_TAB}' is required for a read-only audit and was not found."
            ) from exc
        values = worksheet.get_all_values()
    if not values:
        action = "could not be initialized" if initialize else "is empty in read-only audit mode"
        raise PriceListError(f"'{PRICE_LIST_TAB}' {action}.")

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
        record.setdefault("Search Mode", "Category")
        try:
            record["Target Type"] = parse_target_type(record.get("Target Type"))
            record["Allow Bundle Check"] = parse_bundle_check(record.get("Allow Bundle Check"))
        except ValueError as exc:
            raise PriceListError(f"Price List item '{record['Item Name']}': {exc}") from exc
        for price_header in ("Retail Price (PHP)", "Deal Price (PHP)"):
            record[price_header] = _parse_price(str(record[price_header]))
        rows.append(record)
    return rows
