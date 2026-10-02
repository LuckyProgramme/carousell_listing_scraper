from datetime import datetime, timezone

import pytest
import requests

from deal_finder.models import Evaluation, Listing
from deal_finder.repository import ActiveScanError, RepositoryError, ScanNotFoundError
from deal_finder.supabase_repository import SupabaseRepository, SupabaseSettings


class Response:
    def __init__(self, status_code, payload=None):
        self.status_code = status_code
        self._payload = payload
        self.content = b"x" if payload is not None else b""

    def json(self):
        return self._payload


class Session:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def request(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        return self.response


class QueueSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def request(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        return self.responses.pop(0)


def test_create_scan_maps_supabase_row_without_exposing_key():
    session = Session(
        Response(
            201,
            [{"id": "scan-1", "owner_id": "owner-1", "status": "queued"}],
        )
    )
    repository = SupabaseRepository(
        SupabaseSettings("https://example.supabase.co", "server-secret"),
        session=session,
    )

    scan = repository.create_scan("owner-1")

    assert scan.id == "scan-1"
    assert session.calls[0][1]["json"] == {"owner_id": "owner-1", "status": "queued"}


def test_new_secret_key_is_not_sent_as_bearer_token():
    session = Session(
        Response(
            201,
            [{"id": "scan-1", "owner_id": "owner-1", "status": "queued"}],
        )
    )
    repository = SupabaseRepository(
        SupabaseSettings("https://example.supabase.co", "sb_secret_example"),
        session=session,
    )

    repository.create_scan("owner-1")

    headers = session.calls[0][1]["headers"]
    assert headers["apikey"] == "sb_secret_example"
    assert "Authorization" not in headers


def test_create_scan_turns_database_conflict_into_active_scan_error():
    repository = SupabaseRepository(
        SupabaseSettings("https://example.supabase.co", "server-secret"),
        session=Session(Response(409, {"message": "sensitive provider detail"})),
    )

    with pytest.raises(ActiveScanError, match="already"):
        repository.create_scan("owner-1")


def test_recovery_filters_by_owner_queued_status_and_age():
    session = Session(Response(200, []))
    repository = SupabaseRepository(
        SupabaseSettings("https://example.supabase.co", "sb_secret_example"),
        session=session,
    )

    recovered = repository.recover_stale_queued_scan(
        "owner-1", datetime(2026, 9, 30, 1, 0, tzinfo=timezone.utc)
    )

    assert recovered is None
    params = session.calls[0][1]["params"]
    assert params["owner_id"] == "eq.owner-1"
    assert params["status"] == "eq.queued"
    assert params["created_at"].startswith("lt.2026-09-30T01:00:00")


def test_claim_scan_is_conditioned_on_queued_status():
    session = Session(Response(200, []))
    repository = SupabaseRepository(
        SupabaseSettings("https://example.supabase.co", "sb_secret_example"),
        session=session,
    )

    with pytest.raises(ScanNotFoundError, match="already recovered or started"):
        repository.claim_queued_scan(
            "scan-1", "owner-1", target_snapshot=[{"item_name": "PS5 Slim"}]
        )

    params = session.calls[0][1]["params"]
    assert params["id"] == "eq.scan-1"
    assert params["owner_id"] == "eq.owner-1"
    assert params["status"] == "eq.queued"


def test_fail_queued_scan_is_one_atomic_owner_and_status_scoped_patch():
    session = Session(Response(200, [{"id": "scan-1", "owner_id": "owner-1", "status": "failed"}]))
    repository = SupabaseRepository(
        SupabaseSettings("https://example.supabase.co", "sb_secret_example"), session=session
    )
    before = datetime.now(timezone.utc)
    failed = repository.fail_queued_scan("scan-1", "owner-1", "Safe startup failure.")
    after = datetime.now(timezone.utc)
    assert failed.status == "failed"
    assert len(session.calls) == 1
    args, kwargs = session.calls[0]
    assert args == ("PATCH", "https://example.supabase.co/rest/v1/scan_runs")
    assert kwargs["params"] == {"id": "eq.scan-1", "owner_id": "eq.owner-1", "status": "eq.queued"}
    assert kwargs["json"]["status"] == "failed"
    assert kwargs["json"]["safe_error"] == "Safe startup failure."
    completed_at = datetime.fromisoformat(kwargs["json"]["completed_at"])
    assert completed_at.tzinfo == timezone.utc
    assert before <= completed_at <= after
    assert kwargs["headers"]["Prefer"] == "return=representation"
    assert kwargs["headers"]["apikey"] == "sb_secret_example"
    assert "Authorization" not in kwargs["headers"]
    assert kwargs["timeout"] == 20


def test_fail_queued_scan_returns_none_when_no_eligible_row_remains():
    session = Session(Response(200, []))
    repository = SupabaseRepository(
        SupabaseSettings("https://example.supabase.co", "sb_secret_example"), session=session
    )
    assert repository.fail_queued_scan("scan-1", "owner-1", "Safe error.") is None
    assert len(session.calls) == 1


@pytest.mark.parametrize("operation,status", [("claim", "scanning"), ("fail", "failed")])
@pytest.mark.parametrize("kind", ["empty-body", "object", "multiple", "not-mapping", "missing-id", "missing-owner", "wrong-id", "wrong-owner", "wrong-status", "invalid-count"])
def test_conditional_mutation_requires_a_single_matching_representation(operation, status, kind):
    row = {"id": "scan-1", "owner_id": "owner-1", "status": status}
    payload = [row]
    if kind == "empty-body":
        payload = None
    elif kind == "object":
        payload = {"private": "provider canary"}
    elif kind == "multiple":
        payload = [row, dict(row)]
    elif kind == "not-mapping":
        payload = ["private response canary"]
    elif kind == "missing-id":
        del row["id"]
    elif kind == "missing-owner":
        del row["owner_id"]
    elif kind == "wrong-id":
        row["id"] = "private-wrong-id"
    elif kind == "wrong-owner":
        row["owner_id"] = "private-wrong-owner"
    elif kind == "wrong-status":
        row["status"] = "queued"
    elif kind == "invalid-count":
        row["listings_count"] = "private-invalid-count"
    session = Session(Response(200, payload))
    repository = SupabaseRepository(
        SupabaseSettings("https://example.supabase.co", "sb_secret_example"), session=session
    )
    with pytest.raises(RepositoryError) as caught:
        if operation == "claim":
            repository.claim_queued_scan("scan-1", "owner-1", target_snapshot=[])
        else:
            repository.fail_queued_scan("scan-1", "owner-1", "Safe error.")
    assert len(session.calls) == 1
    assert "private" not in str(caught.value)


@pytest.mark.parametrize("operation", ["claim", "fail"])
def test_mutation_timeout_is_safe_and_never_retried(operation):
    class TimeoutSession(Session):
        def request(self, *args, **kwargs):
            self.calls.append((args, kwargs))
            raise requests.Timeout("private sb_secret_canary provider timeout")
    session = TimeoutSession(None)
    repository = SupabaseRepository(
        SupabaseSettings("https://example.supabase.co", "sb_secret_example"), session=session
    )
    with pytest.raises(RepositoryError) as caught:
        if operation == "claim":
            repository.claim_queued_scan("scan-1", "owner-1", target_snapshot=[])
        else:
            repository.fail_queued_scan("scan-1", "owner-1", "Safe error.")
    assert len(session.calls) == 1
    assert "private" not in str(caught.value)


def test_claim_returns_verified_snapshot_and_owner():
    snapshot = [{"id": "target-1", "item_name": "Console"}]
    session = Session(Response(200, [{"id": "scan-1", "owner_id": "owner-1", "status": "scanning", "target_snapshot": snapshot}]))
    repository = SupabaseRepository(
        SupabaseSettings("https://example.supabase.co", "sb_secret_example"), session=session
    )
    claim = repository.claim_queued_scan("scan-1", "owner-1", target_snapshot=snapshot)
    assert claim.id == "scan-1" and claim.owner_id == "owner-1" and claim.status == "scanning"
    assert list(claim.target_snapshot) == snapshot
    assert session.calls[0][1]["json"]["target_snapshot"] == snapshot


def test_multiple_snapshot_targets_for_one_listing_are_persisted_separately():
    session = QueueSession(
        [
            Response(
                201,
                [
                    {
                        "id": "listing-row-1",
                        "source_listing_id": "source-listing-1",
                    }
                ],
            ),
            Response(201),
        ]
    )
    repository = SupabaseRepository(
        SupabaseSettings("https://example.supabase.co", "sb_secret_example"),
        session=session,
    )
    listing = Listing("source-listing-1", "Console", 100)
    first_target = "11111111-1111-1111-1111-111111111111"
    second_target = "22222222-2222-2222-2222-222222222222"
    evaluations = [
        Evaluation(
            listing_source_id=listing.id,
            target_snapshot_id=first_target,
            target_snapshot={"id": first_target, "item_name": "Console"},
            accepted=False,
        ),
        Evaluation(
            listing_source_id=listing.id,
            target_snapshot_id=second_target,
            target_snapshot={"id": second_target, "item_name": "Console Pro"},
            accepted=False,
        ),
    ]

    saved = repository.save_scan_output(
        "scan-1", "owner-1", [listing], evaluations
    )

    assert saved == {"listings": 1, "evaluations": 2}
    payload = session.calls[1][1]["json"]
    assert {row["target_snapshot_id"] for row in payload} == {
        first_target,
        second_target,
    }
    assert all(row["target_id"] is None for row in payload)
