from dataclasses import replace
from unittest.mock import Mock

import pytest

from deal_finder.deal_engine import CascadeResult, run_two_stage_cascade
from deal_finder.candidate_filter import CandidateMatch
from deal_finder.gemini_auditor import AuditBatchResult
from deal_finder.models import AuditResult, Listing, ScanRun, Target
from deal_finder.repository import RepositoryError, ScanNotFoundError
from deal_finder.scan_service import (
    ScanClaimError,
    ScanExecutionError,
    _build_evaluations,
    run_repository_scan,
)
from deal_finder.scraper import ScrapeBatchResult


class Repository:
    def __init__(self, targets, claim_error=None, scan=None):
        self.targets = targets
        self.claim_error = claim_error
        self.updates = []
        self.saved = None
        self.scan = scan or ScanRun("scan-1", "owner-1", "queued")
        self.calls = []
        self.queued_failures = []

    def get_scan(self, scan_id, owner_id=None):
        self.calls.append(("get_scan", scan_id, owner_id))
        return self.scan

    def list_enabled_targets(self, owner_id):
        self.calls.append(("targets", owner_id))
        return self.targets

    def update_scan(self, scan_id, owner_id, status, **fields):
        self.updates.append((status, fields))
        self.scan = ScanRun(
            scan_id,
            owner_id,
            status,
            listings_count=fields.get("listings_count", 0),
            candidates_count=fields.get("candidates_count", 0),
            deals_count=fields.get("deals_count", 0),
            safe_error=fields.get("safe_error"),
        )
        return self.scan

    def fail_queued_scan(self, scan_id, owner_id, safe_error):
        self.queued_failures.append((scan_id, owner_id, safe_error))
        if self.scan.id != scan_id or self.scan.owner_id != owner_id or self.scan.status != "queued":
            return None
        return self.update_scan(scan_id, owner_id, "failed", safe_error=safe_error)

    def claim_queued_scan(self, scan_id, owner_id, *, target_snapshot):
        if self.claim_error:
            raise self.claim_error
        if self.scan.status != "queued":
            raise ScanNotFoundError("already claimed or recovered")
        self.updates.append(("scanning", {"target_snapshot": target_snapshot}))
        self.scan = replace(self.scan, status="scanning", target_snapshot=tuple(target_snapshot))
        return self.scan

    def save_scan_output(self, scan_id, owner_id, listings, evaluations):
        self.saved = (listings, evaluations)
        return {"listings": len(listings), "evaluations": len(evaluations)}


def test_scan_runs_all_stages_and_persists_output():
    repository = Repository(
        [Target("PS5 Slim", "Video Gaming", 20000, id="target-1", owner_id="owner-1")]
    )
    listing = {
        "id": "listing-1",
        "title": "PS5 Slim",
        "price": 18000,
        "category": "Video Gaming",
        "thumbnail_url": "https://example.com/thumb.jpg",
    }
    scrape = lambda rows: ScrapeBatchResult((listing,), ())
    cascade = lambda listings, rows, **kwargs: CascadeResult(
        deals=(),
        candidates=(),
        listings=tuple(listings),
        audit_result=AuditBatchResult((), (), ()),
    )

    completed = run_repository_scan(
        repository, "scan-1", scrape_targets=scrape, run_cascade=cascade
    )

    assert completed.status == "completed"
    assert [status for status, _ in repository.updates] == [
        "scanning",
        "evaluating",
        "saving",
        "completed",
    ]
    assert repository.saved[0][0].thumbnail_url == "https://example.com/thumb.jpg"


def test_missing_targets_marks_scan_failed_with_safe_message():
    repository = Repository([])

    with pytest.raises(ScanExecutionError, match="invalid"):
        run_repository_scan(repository, "scan-1")

    assert repository.updates[-1][0] == "failed"
    assert "target or listing data was invalid" in repository.updates[-1][1]["safe_error"]
    assert len(repository.queued_failures) == 1


def test_evaluation_uses_snapshot_when_target_is_deleted_mid_scan():
    target = Target(
        "PS5 Slim",
        "Video Gaming",
        20000,
        id="22222222-2222-2222-2222-222222222222",
        owner_id="owner-1",
    )
    listing = Listing("listing-1", "PS5 Slim", 18000)
    candidate = CandidateMatch(listing, target, 18000, 95.0, "normal")
    cascade = CascadeResult(
        deals=(),
        candidates=(candidate,),
        listings=(listing.to_dict(),),
        audit_result=AuditBatchResult((), (), ()),
    )

    evaluation = _build_evaluations(cascade, {target.item_name: target})[0]

    assert evaluation.target_id is None
    assert evaluation.target_snapshot_id == "22222222-2222-2222-2222-222222222222"
    assert evaluation.target_snapshot["id"] == "22222222-2222-2222-2222-222222222222"
    assert evaluation.target_snapshot["deal_price"] == 20000


def test_losing_queued_claim_never_marks_winners_scan_failed():
    target = Target(
        "PS5 Slim",
        "Video Gaming",
        20000,
        id="33333333-3333-3333-3333-333333333333",
        owner_id="owner-1",
    )
    repository = Repository(
        [target],
        claim_error=ScanNotFoundError("already claimed by another worker"),
    )

    with pytest.raises(ScanClaimError, match="already claimed"):
        run_repository_scan(repository, "scan-1")

    assert repository.updates == []
    assert repository.queued_failures == []


def ready_target():
    return Target("PS5 Slim", "Video Gaming", 20000, id="target-1", owner_id="owner-1")


@pytest.mark.parametrize("status", ["scanning", "evaluating", "saving", "completed", "failed"])
def test_nonqueued_reruns_stop_before_targets_or_external_work(status):
    repository = Repository([ready_target()], scan=ScanRun("scan-1", "owner-1", status))
    scrape, cascade = Mock(), Mock()
    with pytest.raises(ScanExecutionError):
        run_repository_scan(repository, "scan-1", scrape_targets=scrape, run_cascade=cascade)
    assert repository.calls == [("get_scan", "scan-1", None)]
    assert repository.updates == repository.queued_failures == []
    scrape.assert_not_called()
    cascade.assert_not_called()


@pytest.mark.parametrize("returned", [ScanRun("scan-1", "other-owner", "queued"), ScanRun("other-scan", "owner-1", "queued")])
def test_owner_scoped_lookup_is_verified_before_target_loading(returned):
    repository = Repository([ready_target()], scan=returned)
    scrape, cascade = Mock(), Mock()
    with pytest.raises((ScanExecutionError, RepositoryError)):
        run_repository_scan(repository, "scan-1", expected_owner_id="owner-1", scrape_targets=scrape, run_cascade=cascade)
    assert repository.calls == [("get_scan", "scan-1", "owner-1")]
    assert repository.updates == repository.queued_failures == []
    scrape.assert_not_called()
    cascade.assert_not_called()


@pytest.mark.parametrize("load_error", [ValueError("private target canary"), RepositoryError("private storage canary")])
def test_preclaim_load_error_uses_only_conditional_failure(monkeypatch, caplog, load_error):
    repository = Repository([ready_target()])
    unconditional = Mock(side_effect=AssertionError("unconditional preclaim failure"))
    conditional = Mock(return_value=ScanRun("scan-1", "owner-1", "failed"))
    monkeypatch.setattr(repository, "update_scan", unconditional)
    monkeypatch.setattr(repository, "fail_queued_scan", conditional)
    monkeypatch.setattr(repository, "list_enabled_targets", Mock(side_effect=load_error))
    scrape, cascade = Mock(), Mock()
    with pytest.raises(ScanExecutionError) as caught:
        run_repository_scan(repository, "scan-1", scrape_targets=scrape, run_cascade=cascade)
    conditional.assert_called_once()
    assert conditional.call_args.args[:2] == ("scan-1", "owner-1")
    unconditional.assert_not_called()
    scrape.assert_not_called()
    cascade.assert_not_called()
    assert "private" not in str(caught.value) + caplog.text
    assert all(record.exc_info is None for record in caplog.records)


@pytest.mark.parametrize("winner_status", ["scanning", "evaluating", "saving", "completed", "failed"])
def test_target_load_failure_cannot_fail_a_claim_or_recovery_winner(monkeypatch, caplog, winner_status):
    repository = Repository([ready_target()])
    def race(owner_id):
        repository.scan = replace(repository.scan, status=winner_status)
        raise RepositoryError("private race detail")
    monkeypatch.setattr(repository, "list_enabled_targets", race)
    scrape, cascade = Mock(), Mock()
    with pytest.raises(ScanExecutionError):
        run_repository_scan(repository, "scan-1", scrape_targets=scrape, run_cascade=cascade)
    assert repository.scan.status == winner_status
    assert len(repository.queued_failures) == 1
    assert repository.updates == []
    scrape.assert_not_called()
    cascade.assert_not_called()
    assert "private" not in caplog.text


@pytest.mark.parametrize("winner_status", ["scanning", "failed"])
def test_target_load_success_then_lost_claim_performs_no_work(monkeypatch, winner_status):
    repository = Repository([ready_target()])
    def race(owner_id):
        repository.scan = replace(repository.scan, status=winner_status)
        return repository.targets
    monkeypatch.setattr(repository, "list_enabled_targets", race)
    scrape, cascade = Mock(), Mock()
    with pytest.raises(ScanClaimError):
        run_repository_scan(repository, "scan-1", scrape_targets=scrape, run_cascade=cascade)
    assert repository.scan.status == winner_status
    assert repository.updates == repository.queued_failures == []
    scrape.assert_not_called()
    cascade.assert_not_called()


def test_ambiguous_claim_response_never_triggers_failure_or_external_work(caplog):
    repository = Repository([ready_target()], claim_error=RepositoryError("private lost claim detail"))
    scrape, cascade = Mock(), Mock()
    with pytest.raises(ScanClaimError) as caught:
        run_repository_scan(repository, "scan-1", scrape_targets=scrape, run_cascade=cascade)
    assert repository.updates == repository.queued_failures == []
    scrape.assert_not_called()
    cascade.assert_not_called()
    assert "private" not in str(caught.value) + caplog.text


def test_failed_preclaim_failure_persistence_is_safe_and_never_retried(monkeypatch, caplog):
    repository = Repository([])
    conditional = Mock(side_effect=RepositoryError("private failure persistence"))
    monkeypatch.setattr(repository, "fail_queued_scan", conditional)
    with pytest.raises(ScanExecutionError):
        run_repository_scan(repository, "scan-1", scrape_targets=Mock(), run_cascade=Mock())
    conditional.assert_called_once()
    assert repository.updates == []
    assert "private" not in caplog.text


def test_postclaim_failure_preserves_worker_owned_failure_and_safe_logs(caplog):
    repository = Repository([ready_target()])
    cascade = Mock()
    with pytest.raises(ScanExecutionError) as caught:
        run_repository_scan(repository, "scan-1", scrape_targets=Mock(side_effect=RuntimeError("private scraper detail")), run_cascade=cascade)
    assert [status for status, _ in repository.updates] == ["scanning", "failed"]
    assert repository.queued_failures == []
    cascade.assert_not_called()
    assert "private" not in str(caught.value) + caplog.text
    assert all(record.exc_info is None for record in caplog.records)


@pytest.mark.parametrize("claim", [None, ScanRun("other-scan", "owner-1", "scanning"), ScanRun("scan-1", "other-owner", "scanning"), ScanRun("scan-1", "owner-1", "queued")])
def test_unproven_claim_representation_does_not_start_work_or_fail_scan(monkeypatch, claim):
    repository = Repository([ready_target()])
    monkeypatch.setattr(repository, "claim_queued_scan", Mock(return_value=claim))
    scrape, cascade = Mock(), Mock()
    with pytest.raises(ScanClaimError):
        run_repository_scan(repository, "scan-1", scrape_targets=scrape, run_cascade=cascade)
    assert repository.updates == repository.queued_failures == []
    scrape.assert_not_called()
    cascade.assert_not_called()


@pytest.mark.parametrize("changed,accepted", [({}, True), ({"confidence": 79}, False), ({"specs_matched": False}, False), ({"is_accessory": True}, False), ({"matched_item": "Other Console"}, False), ({"id": "unknown-listing"}, False), ({"is_bundle": True, "individual_price": 15000, "separately_available": True, "price_evidence": "private invented evidence"}, False)])
def test_hosted_scan_keeps_independent_gemini_gates_snapshot_and_thumbnail(changed, accepted):
    target = Target("PS5 Slim", "Video Gaming", 20000, retail_price=25000, id="33333333-3333-4333-8333-333333333333", owner_id="owner-1")
    repository = Repository([target])
    listing = {"id": "listing-1", "title": "PS5 Slim", "price": 18000, "category": "Video Gaming", "thumbnail_url": "https://example.com/thumb.jpg"}
    values = {"id": "listing-1", "matched_item": "PS5 Slim", "confidence": 95, "specs_matched": True, **changed}
    audit = Mock(return_value=AuditBatchResult((AuditResult(**values),), (), ({"id": "fallback-1", "audit_source": "local"},)))
    def cascade(listings, rows, **kwargs):
        assert kwargs == {"include_local_fallback": False}
        return run_two_stage_cascade(listings, rows, audit_candidates=audit, **kwargs)
    completed = run_repository_scan(repository, "scan-1", scrape_targets=lambda rows: ScrapeBatchResult((listing,), ()), run_cascade=cascade)
    assert completed.status == "completed"
    assert completed.candidates_count == 1
    assert completed.deals_count == int(accepted)
    audit.assert_called_once()
    assert repository.saved[0][0].thumbnail_url == listing["thumbnail_url"]
    evaluation = repository.saved[1][0]
    assert evaluation.accepted is accepted
    assert evaluation.target_id is None
    assert evaluation.target_snapshot_id == target.id
    assert evaluation.target_snapshot["deal_price"] == 20000
    assert evaluation.target_snapshot["retail_price"] == 25000
