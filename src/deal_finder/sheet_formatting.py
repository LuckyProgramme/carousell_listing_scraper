"""Batched, repeatable formatting for deal-finder worksheets."""

from collections.abc import Sequence
from typing import Any
from gspread.utils import rowcol_to_a1


def color(hex_value: str) -> dict[str, float]:
    return dict(zip(('red', 'green', 'blue'), (int(hex_value[i:i + 2], 16) / 255 for i in (1, 3, 5))))


CONDITION_COLORS = {
    'brand new': '#1B5E20', 'like new': '#2E7D32', 'lightly used': '#1565C0',
    'well used': '#995C00', 'heavily used': '#B71C1C',
}


def format_worksheet(worksheet, headers: Sequence[str], rows: Sequence[Sequence[Any]], *, header_row: int = 1) -> None:
    """Style known columns using the actual header layout; coalesce adjacent badges."""
    last = len(headers)
    formats = [{
        'range': f'A{header_row}:{rowcol_to_a1(header_row, last)}',
        'format': {'backgroundColor': color('#1A365D'),
                   'textFormat': {'bold': True, 'foregroundColor': color('#FFFFFF')},
                   'wrapStrategy': 'WRAP'},
    }]
    if rows:
        first_row, end_row = header_row + 1, header_row + len(rows)
        formats.append({'range': f'A{first_row}:{rowcol_to_a1(end_row, last)}',
                        'format': {'backgroundColor': color('#FFFFFF'),
                                   'textFormat': {'bold': False, 'foregroundColor': color('#172B4D')}}})
        for column, header in enumerate(headers, start=1):
            cell_range = f'{rowcol_to_a1(first_row, column)}:{rowcol_to_a1(end_row, column)}'
            if header in {'Carousell Price', 'Deal Price', 'Savings', 'Retail Price (PHP)', 'Deal Price (PHP)'}:
                formats.append({'range': cell_range, 'format': {
                    'textFormat': {'bold': True}, 'numberFormat': {'type': 'CURRENCY', 'pattern': '"₱"#,##0.00'},
                }})
            if header == 'Confidence / Score':
                formats.append({'range': cell_range, 'format': {
                    'backgroundColor': color('#1B5E20'),
                    'textFormat': {'bold': True, 'foregroundColor': color('#FFFFFF')},
                }})
            if header in {'Final Condition', 'Original Condition'}:
                start = 0
                while start < len(rows):
                    def shade(index):
                        value = rows[index][column - 1] if len(rows[index]) >= column else ''
                        return CONDITION_COLORS.get(str(value).strip().casefold())
                    background = shade(start)
                    stop = start + 1
                    while stop < len(rows) and shade(stop) == background:
                        stop += 1
                    if background:
                        formats.append({'range': f'{rowcol_to_a1(first_row + start, column)}:{rowcol_to_a1(first_row + stop - 1, column)}',
                                        'format': {'backgroundColor': color(background), 'textFormat': {'bold': True, 'foregroundColor': color('#FFFFFF')}}})
                    start = stop
    worksheet.batch_format(formats)
    worksheet.freeze(rows=header_row)
