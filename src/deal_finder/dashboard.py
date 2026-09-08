"""Thread-safe dashboard state; independent of browser connections and UI widgets."""

from collections import deque
from collections.abc import Callable, Mapping, Sequence
import logging
from threading import Lock, Thread
from typing import Any

from .deal_finder import SecretRedactingFilter, run_pipeline
from .sheets_handler import open_deal_finder_spreadsheet, read_price_list_rows
from .sheets_writer import write_outputs


class DashboardState:
    def __init__(self):
        self.lock = Lock()
        self.operation_lock = Lock()
        self.running = False
        self.stage = 'Ready to find your next deal'
        self.progress = 0.0
        self.counts = {'scraped': 0, 'candidates': 0, 'deals': 0}
        self.deals: list[dict[str, Any]] = []
        self.logs: deque[tuple[int, str]] = deque(maxlen=500)
        self.sequence = 0
        self.revision = 0
        self.error = ''
        self.summary: dict[str, Any] = {}

    def log(self, message: str):
        with self.lock:
            self.sequence += 1
            self.logs.append((self.sequence, SecretRedactingFilter.redact_secrets(message)))

    def update_progress(self, stage: str, fraction: float, counts: Mapping[str, int]):
        with self.lock:
            self.stage, self.progress = stage, fraction
            self.counts.update(counts)

    def receive_deals(self, deals: Sequence[Mapping[str, Any]]):
        with self.lock:
            self.deals = [dict(deal) for deal in deals]
            self.revision += 1

    def snapshot(self) -> dict[str, Any]:
        with self.lock:
            return {'running': self.running, 'stage': self.stage, 'progress': self.progress,
                    'counts': dict(self.counts), 'deals': list(self.deals), 'logs': list(self.logs),
                    'revision': self.revision, 'error': self.error, 'summary': dict(self.summary)}

    def start(self, spreadsheet_id: str, *, dry_run: bool, pipeline: Callable = run_pipeline) -> bool:
        if not self.operation_lock.acquire(blocking=False):
            return False
        with self.lock:
            self.running = True
            self.error = ''
            self.summary = {}
            self.counts = dict.fromkeys(self.counts, 0)
            self.deals = []
            self.revision += 1
            self.stage, self.progress = 'Connecting to Google Sheets', 0.0

        def worker():
            try:
                workbook = open_deal_finder_spreadsheet(spreadsheet_id)
                summary = pipeline(
                    read_price_list=lambda: read_price_list_rows(workbook, initialize=not dry_run),
                    write_results=lambda deals, listings: write_outputs(deals, listings, workbook),
                    dry_run=dry_run, on_progress=self.update_progress, on_deals=self.receive_deals,
                )
                with self.lock:
                    self.summary = dict(summary)
            except Exception as exc:
                message = SecretRedactingFilter.redact_secrets(str(exc))
                self.log(f'Run failed: {message}')
                with self.lock:
                    self.error, self.stage = message, 'Run failed'
            finally:
                with self.lock:
                    self.running = False
                self.operation_lock.release()

        try:
            Thread(target=worker, name='deal-finder-pipeline', daemon=True).start()
        except Exception:
            with self.lock:
                self.running = False
            self.operation_lock.release()
            raise
        return True


class DashboardLogHandler(logging.Handler):
    def __init__(self, state: DashboardState):
        super().__init__(logging.INFO)
        self.state = state
        self.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s', datefmt='%H:%M:%S'))

    def emit(self, record: logging.LogRecord):
        self.state.log(self.format(record))
