"""Command-line entry point for the Carousell Deal Finder pipeline."""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests

from .config import BASE_DIR
from .deal_engine import CascadeResult, run_two_stage_cascade
from .scraper import ScrapeBatchResult, ScraperError, scrape_price_list_sources
from .sheets_handler import PriceListError, read_price_list_rows
from .sheets_writer import SheetsWriterError, write_outputs


LOG_FILE = Path(BASE_DIR) / "logs" / "deal_finder.log"
AUDIT_LOG_DIR = Path(BASE_DIR) / "logs"

# Patterns for secret redaction in logging
SECRET_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    # Gemini API Key (starts with AIzaSy or AQ. followed by URL-safe chars)
    (re.compile(r"\bAIzaSy[A-Za-z0-9_-]{25,45}\b"), "AIzaSy***[REDACTED_API_KEY]***"),
    (re.compile(r"\bAQ\.[A-Za-z0-9_-]{30,60}\b"), "AQ.***[REDACTED_API_KEY]***"),
    # General sensitive query/header key=value patterns
    (re.compile(r"(?i)(key|api_key|token|secret|password)=([^&\s]+)"), r"\1=***[REDACTED]***"),
    # Bearer tokens
    (re.compile(r"(?i)bearer\s+[A-Za-z0-9._~+/-]{16,}"), "Bearer ***[REDACTED_TOKEN]***"),
    # Google Service Account private keys
    (
        re.compile(r"-----BEGIN (?:RSA )?PRIVATE KEY-----[^-]+-----END (?:RSA )?PRIVATE KEY-----", re.DOTALL),
        "-----BEGIN PRIVATE KEY-----\n***[REDACTED_PRIVATE_KEY]***\n-----END PRIVATE KEY-----",
    ),
    # Service account JSON fields
    (re.compile(r'"private_key":\s*"[^"]+"'), '"private_key": "***[REDACTED]***"'),
)


class SecretRedactingFilter(logging.Filter):
    """Logging filter that redacts API keys, credentials, and private tokens from log messages."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = self.redact_secrets(record.msg)
        if record.args:
            if isinstance(record.args, dict):
                record.args = {k: self.redact_secrets(v) if isinstance(v, str) else v for k, v in record.args.items()}
            elif isinstance(record.args, tuple):
                record.args = tuple(self.redact_secrets(a) if isinstance(a, str) else a for a in record.args)
        return True

    @staticmethod
    def redact_secrets(text: str) -> str:
        if not text or not isinstance(text, str):
            return text
        result = text
        for pattern, replacement in SECRET_PATTERNS:
            result = pattern.sub(replacement, result)
        return result


def configure_logging(log_file: Path = LOG_FILE) -> None:
    """Configure concise console output plus a persistent local run log with secret redaction."""
    logger = logging.getLogger()
    if logger.handlers:
        return
    log_file.parent.mkdir(parents=True, exist_ok=True)
    redacting_filter = SecretRedactingFilter()

    stream_handler = logging.StreamHandler()
    stream_handler.addFilter(redacting_filter)

    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.addFilter(redacting_filter)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[stream_handler, file_handler],
    )
    logger.addFilter(redacting_filter)


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


def write_audit_report(
    cascade: CascadeResult,
    audit_log_dir: Path = AUDIT_LOG_DIR,
) -> Path:
    """Write a PII-minimized comparison artifact for a dry-run/audit execution."""
    audit_log_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    report_path = audit_log_dir / f"audit_run_{timestamp}.json"
    report = {"generated_at": datetime.now(timezone.utc).isoformat(), **cascade.audit_report()}
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8"
    )
    return report_path


def run_pipeline(
    *,
    scrape_targets: Callable[[Sequence[Mapping[str, Any]]], ScrapeBatchResult] = scrape_price_list_sources,
    read_price_list: Callable[[], Sequence[Mapping[str, Any]]] | None = None,
    write_results: Callable[[Sequence[Mapping[str, Any]], Sequence[Mapping[str, Any]]], Mapping[str, int]] = write_outputs,
    run_cascade: Callable[[Iterable[Mapping[str, Any]], Sequence[Mapping[str, Any]]], CascadeResult] = run_two_stage_cascade,
    dry_run: bool = False,
    audit_report_writer: Callable[[CascadeResult, Path], Path] = write_audit_report,
    audit_log_dir: Path = AUDIT_LOG_DIR,
) -> dict[str, Any]:
    """Run scrape → match → write, returning counts suitable for logging or a CLI."""
    reference_rows = (
        read_price_list()
        if read_price_list is not None
        else read_price_list_rows(initialize=not dry_run)
    )
    scrape_batch = scrape_targets(reference_rows)
    listings = list(scrape_batch.listings)
    cascade = run_cascade(
        listings, reference_rows, include_local_fallback=dry_run
    )
    cascade = replace(
        cascade,
        source_summaries=tuple(summary.to_dict() for summary in scrape_batch.source_summaries),
    )
    if cascade.audit_result.whole_batch_fallback:
        logging.warning(
            "Gemini audit fell back after %d attempt(s): model=%s status=%s endpoint=%s reason=%s",
            cascade.audit_result.attempts,
            cascade.audit_result.model or "unknown",
            cascade.audit_result.http_status or "none",
            cascade.audit_result.endpoint or "unknown",
            cascade.audit_result.failure_reason or "no failure reason was supplied",
        )
    elif cascade.audit_result.fallback_ids:
        logging.warning(
            "Gemini audit partially fell back for %d listing(s): model=%s status=%s endpoint=%s",
            len(cascade.audit_result.fallback_ids),
            cascade.audit_result.model or "unknown",
            cascade.audit_result.http_status or "none",
            cascade.audit_result.endpoint or "unknown",
        )
    else:
        logging.info(
            "Gemini audit completed: %d semantic audit(s), %d request attempt(s), model=%s status=%s endpoint=%s.",
            len(cascade.audit_result.audits),
            cascade.audit_result.attempts,
            cascade.audit_result.model or "unknown",
            cascade.audit_result.http_status or "none",
            cascade.audit_result.endpoint or "unknown",
        )
    if dry_run:
        report_path = audit_report_writer(cascade, audit_log_dir)
        write_summary: Mapping[str, int] = {
            "current_deals": 0,
            "all_listings": 0,
            "history_appended": 0,
            "history_updated": 0,
        }
    else:
        write_summary = write_results(cascade.deals, cascade.listings)
        report_path = None
    summary: dict[str, Any] = {
        "scraped": len(cascade.listings),
        "candidates": len(cascade.candidates),
        "deals": len(cascade.deals),
        "dry_run": dry_run,
        **dict(write_summary),
    }
    if report_path is not None:
        summary["audit_report"] = str(report_path)
    logging.info(
        "Pipeline complete: scraped=%d candidates=%d deals=%d history_appended=%d history_updated=%d",
        summary["scraped"],
        summary["candidates"],
        summary["deals"],
        summary.get("history_appended", 0),
        summary.get("history_updated", 0),
    )
    return summary


def main(argv: Sequence[str] | None = None) -> int:
    """Run the pipeline and return a shell-compatible status code."""
    parser = argparse.ArgumentParser(description="Find price-qualified Carousell deals.")
    parser.add_argument(
        "--dry-run",
        "--audit",
        dest="dry_run",
        action="store_true",
        help="Run the cascade and write an audit JSON report without updating Google Sheets.",
    )
    args = parser.parse_args(argv)
    configure_logging()
    try:
        summary = run_pipeline(dry_run=args.dry_run)
    except ScraperError as error:
        logging.error("Scraper failure: %s", error)
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

    if summary["dry_run"]:
        print(
            f"Audit complete: {summary['scraped']} listings scanned, "
            f"{summary['candidates']} candidates, {summary['deals']} accepted deals. "
            f"Report: {summary['audit_report']}"
        )
    else:
        print(
            f"Done: {summary['scraped']} listings scanned, {summary['deals']} deals found."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
