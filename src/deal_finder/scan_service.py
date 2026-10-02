"""Reusable scan orchestration for the CLI and hosted workers."""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterable, Mapping, Sequence
from typing import Any

from .deal_engine import CascadeResult, run_two_stage_cascade
from .models import AuditResult, Evaluation, Listing, ScanRun, Target
from .repository import DealRepository, RepositoryError
from .scan_errors import ScanClaimError, ScanExecutionError, ScanNotQueuedError
from .scraper import ScrapeBatchResult, ScraperError, scrape_price_list_sources


def _target_snapshot(target: Target) -> dict[str, Any]:
    return {
        "id": target.id,
        "item_name": target.item_name,
        "category": target.category,
        "search_mode": target.search_mode,
        "deal_price": target.deal_price,
        "retail_price": target.retail_price,
        "downsizing_keywords": list(target.downsizing_keywords),
        "freebie_keywords": list(target.freebie_keywords),
        "notes": target.notes,
        "target_type": target.target_type,
        "allow_bundle_check": target.allow_bundle_check,
    }


def _safe_failure_message(error: BaseException) -> str:
    if isinstance(error, ScraperError):
        return "Carousell could not be scanned safely. Please try again later."
    if isinstance(error, RepositoryError):
        return "Saved data is temporarily unavailable. Please try again later."
    if isinstance(error, ValueError):
        return "The scan stopped because target or listing data was invalid."
    return "The scan failed unexpectedly. Please try again."


def _build_evaluations(
    cascade: CascadeResult,
    target_by_name: Mapping[str, Target],
) -> tuple[Evaluation, ...]:
    audits: dict[str, AuditResult] = {
        audit.id: audit for audit in cascade.audit_result.audits
    }
    deals = {
        (
            str(deal.get("id") or deal.get("listing_id") or "").strip(),
            str(deal.get("matched_item") or "").strip(),
        ): deal
        for deal in cascade.deals
    }
    evaluations: list[Evaluation] = []
    for candidate in cascade.candidates:
        listing = candidate.listing
        target = candidate.target
        audit = audits.get(listing.id)
        deal = deals.get((listing.id, target.item_name))
        accepted = deal is not None
        canonical_target = target_by_name.get(target.item_name, target)
        evaluations.append(
            Evaluation(
                listing_source_id=listing.source_id,
                target_snapshot_id=str(canonical_target.id),
                accepted=accepted,
                matched_item=target.item_name,
                # Evaluations are immutable historical facts. The snapshot is
                # authoritative so deleting a target mid-scan cannot break save.
                target_id=None,
                target_snapshot=_target_snapshot(canonical_target),
                audit_source=(
                    str(deal.get("audit_source")) if accepted else "gemini" if audit else None
                ),  # type: ignore[arg-type]
                confidence=(
                    int(deal["gemini_confidence"])
                    if accepted and deal.get("gemini_confidence") is not None
                    else audit.confidence if audit else None
                ),
                specs_matched=(
                    bool(deal["specs_matched"])
                    if accepted and deal.get("specs_matched") is not None
                    else audit.specs_matched if audit else None
                ),
                local_match_score=(
                    float(deal["local_match_score"])
                    if accepted and deal.get("local_match_score") is not None
                    else None
                ),
                issues=tuple(deal.get("issues") or ()) if accepted else audit.issues if audit else (),
                freebies=tuple(deal.get("freebies") or ()) if accepted else audit.freebies if audit else (),
                final_condition=(
                    str(deal.get("final_condition") or listing.condition) if accepted else listing.condition
                ),
                condition_overridden=bool(deal.get("condition_overridden", False)) if accepted else False,
                deal_price=target.deal_price,
                retail_price=target.retail_price,
                evaluated_price=(
                    float(deal.get("price", deal.get("carousell_price")))
                    if accepted
                    else candidate.effective_price
                ),
                savings=float(deal["savings"]) if accepted and deal.get("savings") is not None else None,
                acceptance_reason=str(deal.get("acceptance_reason") or "") or None if accepted else None,
                is_bundle=bool(deal.get("is_bundle", False)) if accepted else bool(audit.is_bundle) if audit else False,
                individual_price=(
                    float(deal["individual_price"])
                    if accepted and deal.get("individual_price") is not None
                    else audit.individual_price if audit else None
                ),
                price_evidence=(
                    str(deal.get("price_evidence") or "") or None
                    if accepted
                    else audit.price_evidence if audit else None
                ),
            )
        )
    return tuple(evaluations)


def run_repository_scan(
    repository: DealRepository,
    scan_id: str,
    *,
    expected_owner_id: str | None = None,
    scrape_targets: Callable[[Sequence[Mapping[str, Any]]], ScrapeBatchResult] = scrape_price_list_sources,
    run_cascade: Callable[..., CascadeResult] = run_two_stage_cascade,
) -> ScanRun:
    """Execute one already-queued scan and persist every lifecycle stage."""
    scan = (
        repository.get_scan(scan_id, expected_owner_id)
        if expected_owner_id is not None
        else repository.get_scan(scan_id)
    )
    if scan.id != scan_id or not scan.owner_id or (
        expected_owner_id is not None and scan.owner_id != expected_owner_id
    ):
        raise ScanExecutionError("The scan could not be verified for this owner.")
    owner_id = scan.owner_id
    if scan.status != "queued":
        raise ScanNotQueuedError("This scan is no longer queued.")

    def mark_failed(error: BaseException, *, claimed: bool) -> ScanExecutionError:
        safe_message = _safe_failure_message(error)
        logging.error("Scan %s failed: %s", scan_id, safe_message)
        try:
            if claimed:
                repository.update_scan(scan_id, owner_id, "failed", safe_error=safe_message)
            else:
                repository.fail_queued_scan(scan_id, owner_id, safe_message)
        except Exception:
            # The write could have committed before its response was lost.
            # Do not retry, fall back to an unconditional update, or log causes.
            logging.error("Could not confirm failed state for scan %s", scan_id)
        return ScanExecutionError(safe_message)

    try:
        targets = tuple(repository.list_enabled_targets(owner_id))
        if not targets:
            raise ValueError("No enabled targets are configured.")
        snapshots = tuple(_target_snapshot(target) for target in targets)
    except Exception as exc:
        raise mark_failed(exc, claimed=False) from None

    # Claim separately. Any error here is ambiguous: the database may have
    # committed the transition even if the response was lost. Never write a
    # failed status from a worker that cannot prove it owns the queued claim.
    try:
        claimed = repository.claim_queued_scan(
            scan_id,
            owner_id,
            target_snapshot=list(snapshots),
        )
        if claimed.id != scan_id or claimed.owner_id != owner_id or claimed.status != "scanning":
            raise RepositoryError("The scan claim was not confirmed.")
    except Exception:
        raise ScanClaimError(
            "This queued scan was already claimed, recovered, or could not be claimed safely."
        ) from None

    try:
        scanner_rows = [target.to_scanner_mapping() for target in targets]
        scrape_batch = scrape_targets(scanner_rows)
        repository.update_scan(
            scan_id,
            owner_id,
            "evaluating",
            listings_count=len(scrape_batch.listings),
        )
        cascade = run_cascade(scrape_batch.listings, scanner_rows, include_local_fallback=False)
        repository.update_scan(
            scan_id,
            owner_id,
            "saving",
            candidates_count=len(cascade.candidates),
            deals_count=len(cascade.deals),
        )
        listings = tuple(Listing.from_mapping(row) for row in cascade.listings)
        target_by_name = {target.item_name: target for target in targets}
        evaluations = _build_evaluations(cascade, target_by_name)
        repository.save_scan_output(scan_id, owner_id, listings, evaluations)
        return repository.update_scan(
            scan_id,
            owner_id,
            "completed",
            listings_count=len(listings),
            candidates_count=len(cascade.candidates),
            deals_count=len(cascade.deals),
            safe_error=None,
        )
    except Exception as exc:
        raise mark_failed(exc, claimed=True) from None
