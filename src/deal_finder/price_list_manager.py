"""Validated per-row Price List editing with stale-data detection."""

from dataclasses import dataclass
import math
from typing import Any

from gspread.utils import rowcol_to_a1
from .config import PRICE_LIST_TAB
from .models import parse_bundle_check, parse_target_type
from .scraper import build_scrape_sources
from .sheets_handler import PRICE_LIST_HEADERS, PriceListError, _find_header_row
from .sheet_formatting import format_worksheet


@dataclass
class Catalog:
    values: list[list[Any]]
    header_index: int
    headers: list[str]
    records: list[dict[str, Any]]


def load_catalog(spreadsheet) -> Catalog:
    values = spreadsheet.worksheet(PRICE_LIST_TAB).get_all_values()
    found = _find_header_row(values)
    if found is None:
        raise PriceListError('Price List is empty or missing required headers. Use Initialize Price List for an empty tab.')
    header_index, headers = found
    records = []
    for index, row in enumerate(values[header_index + 1:], start=header_index + 2):
        record = {header: row[col] if col < len(row) else '' for col, header in enumerate(headers) if header in PRICE_LIST_HEADERS}
        if str(record.get('Item Name', '')).strip():
            records.append({**record, '_row': index})
    return Catalog(values, header_index, headers, records)


def validate_item(item: dict[str, Any]) -> dict[str, Any]:
    item = {key: item.get(key, '') for key in PRICE_LIST_HEADERS}
    item['Item Name'] = str(item['Item Name']).strip()
    if not item['Item Name']:
        raise PriceListError('Item Name is required.')
    for key in ('Deal Price (PHP)', 'Retail Price (PHP)'):
        raw = item[key]
        if key == 'Retail Price (PHP)' and (raw is None or str(raw).strip() == ''):
            item[key] = ''
            continue
        try:
            price = float(str(raw).replace(',', ''))
        except (TypeError, ValueError) as exc:
            raise PriceListError(f'{key} must be a positive number.') from exc
        if not math.isfinite(price) or price <= 0:
            raise PriceListError(f'{key} must be a positive number.')
        item[key] = price
    item['Search Mode'] = str(item['Search Mode'] or 'Category').strip()
    item['Target Type'] = parse_target_type(item['Target Type'])
    item['Allow Bundle Check'] = parse_bundle_check(item['Allow Bundle Check'])
    build_scrape_sources([item])
    return item


def save_catalog_item(spreadsheet, catalog: Catalog, item: dict[str, Any] | None, *, row_number: int | None = None) -> Catalog:
    """Update/clear only owned cells, preserving custom columns and neighboring rows."""
    worksheet = spreadsheet.worksheet(PRICE_LIST_TAB)
    if worksheet.get_all_values() != catalog.values:
        raise PriceListError('Price List changed since loading. Reload it before saving to avoid overwriting newer edits.')
    if row_number is not None and row_number not in {record['_row'] for record in catalog.records}:
        raise PriceListError('Selected row is no longer available. Reload Price List.')
    if item is None and row_number is None:
        raise PriceListError('Select an item to delete.')
    normalized = validate_item(item) if item is not None else None
    records = [record for record in catalog.records if record['_row'] != row_number]
    if normalized is not None:
        # Validate duplicate item names and the combined search plan before any writes.
        build_scrape_sources([*records, normalized])
    headers = list(catalog.headers)
    updates = []
    if normalized is not None:
        for header in PRICE_LIST_HEADERS:
            if header not in headers:
                headers.append(header)
                updates.append({'range': rowcol_to_a1(catalog.header_index + 1, len(headers)), 'values': [[header]]})
    target_row = row_number or len(catalog.values) + 1
    for column, header in enumerate(headers, start=1):
        if header in PRICE_LIST_HEADERS:
            updates.append({'range': rowcol_to_a1(target_row, column), 'values': [[normalized[header] if normalized is not None else '']]})
    if worksheet.row_count < target_row or worksheet.col_count < len(headers):
        worksheet.resize(rows=max(worksheet.row_count, target_row), cols=max(worksheet.col_count, len(headers)))
    worksheet.batch_update(updates, value_input_option='RAW')
    updated = load_catalog(spreadsheet)
    format_worksheet(worksheet, updated.headers, updated.values[updated.header_index + 1:], header_row=updated.header_index + 1)
    return updated
