"""Local NiceGUI dashboard. Launch with ``deal-finder-ui``."""

from __future__ import annotations

import argparse
import logging
from typing import Any
from urllib.parse import urlsplit

from nicegui import run, ui

from .config import SPREADSHEET_ID
from .dashboard import DashboardLogHandler, DashboardState
from .deal_finder import SecretRedactingFilter, configure_logging
from .metadata import http_url
from .price_list_manager import load_catalog, save_catalog_item
from .sheet_formatting import CONDITION_COLORS
from .sheets_handler import (
    PRICE_LIST_HEADERS, ensure_price_list_tab, extract_spreadsheet_id,
    get_service_account_email, open_deal_finder_spreadsheet, validate_sheet_permissions,
)

STATE = DashboardState()


def money(value: Any) -> str:
    return f'₱{float(value or 0):,.0f}'


def carousell_link(value: Any) -> str | None:
    url = http_url(value)
    if url and urlsplit(url).hostname in {'carousell.ph', 'www.carousell.ph'}:
        return url
    return None


def render_deal(deal: dict[str, Any]) -> None:
    with ui.card().classes('w-full overflow-hidden rounded-xl p-0 shadow-sm border border-slate-200'):
        thumbnail = http_url(deal.get('thumbnail_url'))
        if thumbnail:
            ui.image(thumbnail).classes('w-full h-48').props('fit=cover')
        else:
            with ui.row().classes('w-full h-48 bg-slate-100 items-center justify-center'):
                ui.icon('photo_camera', size='3rem').classes('text-slate-300')
        with ui.column().classes('p-5 w-full gap-2'):
            with ui.row().classes('w-full justify-between items-center'):
                ui.badge(f"Save {money(deal.get('savings'))}", color='green-9')
                condition = deal.get('final_condition') or deal.get('condition') or 'Condition unknown'
                ui.badge(condition).style(f'background:{CONDITION_COLORS.get(condition.casefold(), "#64748B")}')
            ui.label(deal.get('title', 'Untitled listing')).classes('text-lg font-semibold leading-tight')
            ui.label(deal.get('matched_item', '')).classes('text-sm text-slate-500')
            ui.label(money(deal.get('carousell_price', deal.get('price')))).classes('text-2xl font-bold text-slate-900')
            ui.label(f"Target {money(deal.get('deal_price'))} · savings against your target").classes('text-xs text-slate-500')
            if deal.get('audit_source') == 'gemini':
                ui.badge(f"Gemini confidence {deal.get('gemini_confidence', 0)}%", color='green-9')
            else:
                ui.badge(f"Local lexical match {float(deal.get('local_match_score') or 0):.1f}%", color='orange-9')
            seller = deal.get('seller') or 'Seller unavailable'
            rating = deal.get('seller_rating')
            if rating is not None:
                seller += f" · ★ {float(rating):.1f}"
                if deal.get('seller_rating_count') is not None:
                    seller += f" ({deal['seller_rating_count']} reviews)"
            ui.label(seller).classes('text-sm text-slate-600')
            if deal.get('like_count') is not None:
                ui.label(f"♡ {deal['like_count']} likes").classes('text-xs text-slate-500')
            if deal.get('location'):
                ui.label(f"Meetup: {deal['location']}").classes('text-sm text-slate-600')
            if deal.get('listing_timestamp'):
                ui.label(f"Listed: {deal['listing_timestamp']}").classes('text-xs text-slate-500')
            for field, label in [('freebies', 'Freebies'), ('issues', 'Issues')]:
                value = deal.get(field)
                if value:
                    ui.label(f'{label}: ' + (value if isinstance(value, str) else ', '.join(value))).classes('text-sm')
            link = carousell_link(deal.get('link'))
            if link:
                ui.link('View on Carousell ↗', link, new_tab=True).classes('font-semibold mt-2')


@ui.page('/')
def dashboard_page():
    ui.colors(primary='#1A365D', positive='#1B5E20')
    ui.query('body').classes('bg-slate-50 text-slate-800')
    catalog = None
    catalog_sheet_id = ''
    selected_row = None
    fields = {}
    last_log = 0
    last_revision = -1

    def report_error(exc):
        message = SecretRedactingFilter.redact_secrets(str(exc))
        STATE.log(message)
        ui.notify(message, type='negative', timeout=10000)

    async def sheet_operation(callback):
        if not STATE.operation_lock.acquire(blocking=False):
            raise RuntimeError('A run or Price List operation is in progress. Wait for it to finish.')
        def guarded_operation():
            try:
                return callback()
            finally:
                STATE.operation_lock.release()
        return await run.io_bound(guarded_operation)

    def sheet_id():
        return extract_spreadsheet_id(sheet_input.value)

    async def validate():
        try:
            result = await run.io_bound(validate_sheet_permissions, sheet_id())
            connection_status.set_text(
                f'Connected: {result.spreadsheet_title}. {result.diagnostic_guidance or ""}'
                if result.valid else f'{result.error_message} {result.diagnostic_guidance or ""}'
            )
        except Exception as exc:
            report_error(exc)

    def start_run():
        try:
            if not STATE.start(sheet_id(), dry_run=bool(audit_only.value)):
                ui.notify('A run or Price List operation is already in progress.', type='warning')
            refresh_status()
        except Exception as exc:
            report_error(exc)

    @ui.refreshable
    def deal_cards():
        data = STATE.snapshot()
        deals = data['deals']
        query = str(search.value or '').casefold()
        deals = [d for d in deals if query in f"{d.get('title', '')} {d.get('matched_item', '')}".casefold()]
        deals.sort(key=lambda d: float(d.get('savings') or 0), reverse=True)
        if not deals:
            with ui.column().classes('w-full items-center py-16 text-slate-500'):
                ui.icon('search', size='3rem')
                ui.label('No matching deals yet').classes('text-xl font-semibold')
                ui.label('Run a search using your Price List, or adjust the filter.')
        else:
            with ui.element('div').classes('grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-5 w-full'):
                for deal in deals:
                    render_deal(deal)

    def fill_form(row_number=None):
        nonlocal selected_row
        selected_row = row_number
        record = next((r for r in catalog.records if r['_row'] == row_number), {}) if catalog else {}
        for header, widget in fields.items():
            value = record.get(header, '')
            if header == 'Allow Bundle Check':
                value = str(value).casefold() in {'true', 'yes', '1'}
            elif header == 'Search Mode':
                value = value or 'Category'
            elif header == 'Target Type':
                value = value or 'Hardware'
            widget.set_value(value)

    def show_catalog():
        selector.set_options({r['_row']: r['Item Name'] for r in catalog.records}, value=None)
        catalog_status.set_text(f'{len(catalog.records)} targets loaded. Select an item to edit, or add a new item.')
        fill_form()

    def new_item():
        selector.set_value(None)
        fill_form()

    async def reload_catalog():
        nonlocal catalog, catalog_sheet_id
        try:
            target_id = sheet_id()
            catalog = await sheet_operation(lambda: load_catalog(open_deal_finder_spreadsheet(target_id)))
            catalog_sheet_id = target_id
            show_catalog()
        except Exception as exc:
            report_error(exc)

    async def initialize_catalog():
        try:
            target_id = sheet_id()
            await sheet_operation(lambda: ensure_price_list_tab(open_deal_finder_spreadsheet(target_id)))
            await reload_catalog()
        except Exception as exc:
            report_error(exc)

    async def save_item(delete=False):
        nonlocal catalog
        try:
            if catalog is None or catalog_sheet_id != sheet_id():
                raise ValueError('Load the Price List for this spreadsheet before editing.')
            item = None if delete else {header: widget.value for header, widget in fields.items()}
            snapshot, row_number, target_id = catalog, selected_row, catalog_sheet_id
            catalog = await sheet_operation(lambda: save_catalog_item(
                open_deal_finder_spreadsheet(target_id), snapshot, item, row_number=row_number))
            show_catalog()
            ui.notify('Item deleted.' if delete else 'Item saved.', type='positive')
        except Exception as exc:
            report_error(exc)

    async def confirm_delete():
        if selected_row is None:
            ui.notify('Select an item first.', type='warning')
            return
        with ui.dialog() as dialog, ui.card():
            ui.label(f"Delete {fields['Item Name'].value} from your Price List?")
            with ui.row():
                ui.button('Cancel', on_click=lambda: dialog.submit(False)).props('flat')
                ui.button('Delete item', on_click=lambda: dialog.submit(True), color='negative')
        if await dialog:
            await save_item(delete=True)

    with ui.header().classes('px-6 py-4 items-center'):
        ui.icon('local_offer', size='2rem')
        ui.label('Deal Finder').classes('text-xl font-bold')
        ui.space()
        ui.button('Live logs', icon='terminal', on_click=lambda: log_drawer.toggle()).props('flat color=white')
    with ui.right_drawer(value=False).classes('w-96 bg-slate-900 text-white') as log_drawer:
        ui.label('Live activity').classes('text-lg font-bold')
        log_view = ui.log(max_lines=500).classes('w-full h-full text-xs')

    with ui.column().classes('w-full max-w-7xl mx-auto p-4 md:p-8 gap-6'):
        with ui.row().classes('w-full items-center justify-between'):
            with ui.column().classes('gap-1'):
                ui.label('Find the price worth waiting for.').classes('text-3xl font-bold')
                ui.label('Your Carousell watchlist, checked against your target prices.').classes('text-slate-500')
            run_button = ui.button('Run deal finder', icon='play_arrow', on_click=start_run).classes('px-5 py-2')
        with ui.expansion('Google Sheets connection', icon='table_chart', value=True).classes('w-full bg-white rounded-lg border'):
            sheet_input = ui.input('Google Sheets URL or ID', value=SPREADSHEET_ID).classes('w-full')
            ui.label(f"Share your sheet as Editor with: {get_service_account_email() or 'the client_email in your service account JSON'}").classes('text-sm')
            with ui.row().classes('items-center'):
                ui.button('Validate connection', on_click=validate).props('outline')
                audit_only = ui.switch('Audit only (no Sheet writes)', value=True)
            connection_status = ui.label('Validate connection to check access.').classes('text-sm text-slate-500')
        with ui.tabs().classes('w-full') as tabs:
            deals_tab = ui.tab('Deals', icon='local_offer')
            price_tab = ui.tab('Price List', icon='edit_note')
        with ui.tab_panels(tabs, value=deals_tab).classes('w-full bg-transparent'):
            with ui.tab_panel(deals_tab).classes('p-0'):
                with ui.row().classes('w-full gap-4'):
                    counters = {}
                    for key, title in [('scraped', 'Listings scanned'), ('candidates', 'Candidates'), ('deals', 'Deals found')]:
                        with ui.card().classes('flex-1 min-w-40 shadow-sm border border-slate-200'):
                            ui.label(title).classes('text-slate-500')
                            counters[key] = ui.label('0').classes('text-3xl font-bold')
                stage = ui.label(STATE.snapshot()['stage']).classes('mt-4 text-sm')
                progress = ui.linear_progress(value=0, show_value=False, size='8px').classes('w-full')
                error_label = ui.label().classes('text-red-800 whitespace-pre-wrap')
                result_label = ui.label().classes('text-sm text-slate-500')
                search = ui.input('Filter deals', on_change=lambda: deal_cards.refresh()).props('outlined clearable').classes('w-full my-4')
                deal_cards()
            with ui.tab_panel(price_tab).classes('p-0'):
                ui.label('Manage your target prices').classes('text-xl font-bold')
                ui.label('Save writes one item to Google Sheets. Reload to see edits made elsewhere.').classes('text-slate-500')
                with ui.row():
                    ui.button('Load / reload Price List', on_click=reload_catalog, icon='refresh')
                    ui.button('Initialize empty Price List', on_click=initialize_catalog).props('outline')
                catalog_status = ui.label('Load your Price List to begin.').classes('text-sm')
                selector = ui.select({}, label='Select an existing item', on_change=lambda e: fill_form(e.value)).classes('w-full')
                ui.button('Add new item', icon='add', on_click=new_item).props('flat')
                with ui.element('div').classes('grid grid-cols-1 md:grid-cols-2 gap-4 w-full'):
                    for header in PRICE_LIST_HEADERS:
                        if header == 'Search Mode':
                            fields[header] = ui.select(['Category', 'Item Name'], label=header, value='Category')
                        elif header == 'Target Type':
                            fields[header] = ui.select(['Hardware', 'Game'], label=header, value='Hardware')
                        elif header == 'Allow Bundle Check':
                            fields[header] = ui.checkbox(header)
                        else:
                            fields[header] = ui.input(header)
                with ui.row():
                    ui.button('Save item', icon='save', on_click=lambda: save_item())
                    ui.button('Delete selected item', icon='delete', color='negative', on_click=confirm_delete).props('outline')

    def refresh_status():
        nonlocal last_log, last_revision
        data = STATE.snapshot()
        stage.set_text(data['stage'])
        progress.set_value(data['progress'])
        error_label.set_text(data['error'])
        for key, widget in counters.items():
            widget.set_text(str(data['counts'][key]))
        run_button.set_enabled(not data['running'])
        sheet_input.set_enabled(not data['running'])
        audit_only.set_enabled(not data['running'])
        summary = data['summary']
        result_label.set_text(
            f"Audit results · {summary.get('audit_report', '')}" if summary.get('dry_run')
            else ('Results saved to Google Sheets.' if summary else '')
        )
        for sequence, message in data['logs']:
            if sequence > last_log:
                log_view.push(message)
                last_log = sequence
        if data['revision'] != last_revision:
            last_revision = data['revision']
            deal_cards.refresh()

    ui.timer(0.3, refresh_status)


def main(argv=None):
    parser = argparse.ArgumentParser(description='Open the local Deal Finder dashboard.')
    parser.add_argument('--port', type=int, default=8080)
    parser.add_argument('--no-browser', action='store_true')
    args = parser.parse_args(argv)
    configure_logging()
    logging.getLogger().addHandler(DashboardLogHandler(STATE))
    logging.getLogger().setLevel(logging.INFO)
    ui.run(host='127.0.0.1', port=args.port, title='Deal Finder', reload=False, show=not args.no_browser)


if __name__ == '__main__':
    main()
