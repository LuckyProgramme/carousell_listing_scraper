import pytest

from deal_finder.dispatcher import (
    AuthenticatedUser,
    AuthenticationDependencyError,
    AuthenticationError,
    AuthorizationError,
    JobLaunchError,
    SupabaseTokenVerifier,
    create_app,
)
from deal_finder.models import ScanRun
from deal_finder.repository import ActiveScanError, RepositoryError


class Verifier:
    def __init__(self, error=None):
        self.error = error

    def verify(self, authorization):
        if self.error:
            raise self.error
        assert authorization == "Bearer valid-token"
        return AuthenticatedUser("owner-1", "dealfinder0322@gmail.com")


class Launcher:
    def __init__(self, error=None):
        self.error = error
        self.launched = []

    def launch(self, scan_id):
        if self.error:
            raise self.error
        self.launched.append(scan_id)


class Repository:
    def __init__(self, create_error=None, recover_result=None):
        self.create_error = create_error
        self.recover_result = recover_result
        self.updates = []
        self.recovery_calls = []

    def create_scan(self, owner_id):
        if self.create_error:
            raise self.create_error
        return ScanRun("scan-1", owner_id, "queued")

    def update_scan(self, scan_id, owner_id, status, **fields):
        self.updates.append((scan_id, owner_id, status, fields))
        return ScanRun(scan_id, owner_id, status, safe_error=fields.get("safe_error"))

    def recover_stale_queued_scan(self, owner_id, older_than):
        self.recovery_calls.append((owner_id, older_than))
        return self.recover_result

    def fail_queued_scan(self, scan_id, owner_id, safe_error):
        return self.update_scan(scan_id, owner_id, "failed", safe_error=safe_error)


class AuthResponse:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self.payload = payload

    def json(self):
        return self.payload


class AuthSession:
    def __init__(self, response):
        self.response = response

    def get(self, *args, **kwargs):
        return self.response


def client(repository=None, verifier=None, launcher=None):
    app = create_app(
        repository=repository or Repository(),
        verifier=verifier or Verifier(),
        launcher=launcher or Launcher(),
    )
    app.testing = True
    return app.test_client()


def test_health_is_public():
    response = client().get("/health")
    assert response.status_code == 200
    assert response.json == {"data": {"status": "ok"}}


def test_token_verifier_rejects_missing_and_expired_tokens():
    verifier = SupabaseTokenVerifier(
        "https://example.supabase.co",
        "publishable",
        "dealfinder0322@gmail.com",
        session=AuthSession(AuthResponse(401, {})),
    )
    with pytest.raises(AuthenticationError):
        verifier.verify("")
    with pytest.raises(AuthenticationError, match="expired"):
        verifier.verify("Bearer expired-token")


def test_token_verifier_enforces_exact_email_allowlist():
    verifier = SupabaseTokenVerifier(
        "https://example.supabase.co",
        "publishable",
        "dealfinder0322@gmail.com",
        session=AuthSession(
            AuthResponse(200, {"id": "other-user", "email": "other@example.com"})
        ),
    )
    with pytest.raises(AuthorizationError):
        verifier.verify("Bearer valid-token")


def test_scan_requires_valid_authentication():
    response = client(verifier=Verifier(AuthenticationError("expired"))).post("/v1/scans")
    assert response.status_code == 401
    assert response.json["error"]["code"] == "unauthenticated"


def test_scan_rejects_non_allowlisted_account():
    response = client(verifier=Verifier(AuthorizationError("not allowed"))).post(
        "/v1/scans", headers={"Authorization": "Bearer valid-token"}
    )
    assert response.status_code == 403
    assert response.json["error"]["code"] == "forbidden"


def test_auth_dependency_failure_is_503():
    response = client(
        verifier=Verifier(AuthenticationDependencyError("provider internals"))
    ).post("/v1/scans", headers={"Authorization": "Bearer valid-token"})
    assert response.status_code == 503
    assert response.json["error"]["code"] == "authentication_unavailable"
    assert "provider internals" not in response.get_data(as_text=True)


def test_scan_starts_job_and_returns_accepted():
    launcher = Launcher()
    response = client(launcher=launcher).post(
        "/v1/scans", headers={"Authorization": "Bearer valid-token"}
    )
    assert response.status_code == 202
    assert response.json["data"]["scan"] == {"id": "scan-1", "status": "queued"}
    assert launcher.launched == ["scan-1"]


def test_active_scan_conflict_is_409():
    response = client(
        repository=Repository(ActiveScanError("A scan is already queued or running."))
    ).post("/v1/scans", headers={"Authorization": "Bearer valid-token"})
    assert response.status_code == 409
    assert response.json["error"]["code"] == "scan_already_active"


def test_storage_dependency_failure_is_safe_503():
    response = client(repository=Repository(RepositoryError("database internals"))).post(
        "/v1/scans", headers={"Authorization": "Bearer valid-token"}
    )
    assert response.status_code == 503
    assert response.json["error"]["code"] == "storage_unavailable"
    assert "database internals" not in response.get_data(as_text=True)


def test_job_launch_failure_marks_scan_failed():
    repository = Repository()
    response = client(
        repository=repository,
        launcher=Launcher(JobLaunchError("provider internals")),
    ).post("/v1/scans", headers={"Authorization": "Bearer valid-token"})
    assert response.status_code == 503
    assert response.json["error"]["code"] == "scanner_unavailable"
    assert repository.updates[0][2] == "failed"
    assert "provider internals" not in response.get_data(as_text=True)


def test_recover_stale_queued_scan_returns_versioned_contract():
    recovered = ScanRun("scan-1", "owner-1", "failed")
    repository = Repository(recover_result=recovered)

    response = client(repository=repository).post(
        "/v1/scans/recover-queued",
        headers={"Authorization": "Bearer valid-token"},
    )

    assert response.status_code == 200
    assert response.json == {
        "data": {
            "recovered": True,
            "scan": {"id": "scan-1", "status": "failed"},
        }
    }
    assert repository.recovery_calls[0][0] == "owner-1"


def test_recovery_does_not_claim_recent_or_running_scan():
    response = client(repository=Repository(recover_result=None)).post(
        "/v1/scans/recover-queued",
        headers={"Authorization": "Bearer valid-token"},
    )
    assert response.status_code == 200
    assert response.json == {"data": {"recovered": False, "scan": None}}


def test_recovery_requires_authentication():
    response = client(verifier=Verifier(AuthenticationError("expired"))).post(
        "/v1/scans/recover-queued"
    )
    assert response.status_code == 401
    assert response.json["error"]["code"] == "unauthenticated"
