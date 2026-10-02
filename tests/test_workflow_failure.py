"""Offline contracts for the dependency-free setup failure finalizer."""

import base64
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import sys
from unittest.mock import Mock
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlsplit

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCAN_ID = "00000000-0000-4000-8000-000000000001"
OWNER_ID = "749743db-c366-47c9-9373-bec966857b32"
OTHER_ID = "00000000-0000-4000-8000-000000000002"


@pytest.fixture
def helper(monkeypatch):
    path = ROOT / "scripts" / "fail_queued_scan.py"
    assert path.exists(), "The standard-library setup failure helper is missing."
    spec = importlib.util.spec_from_file_location("workflow_failure_helper", path)
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, spec.name, module)
    spec.loader.exec_module(module)
    # Tests must never fall through to a real standard-library HTTP request.
    monkeypatch.setattr(module, "build_opener", Mock(side_effect=AssertionError("Unmocked HTTP blocked")))
    return module


@pytest.fixture
def settings():
    return {
        "SCAN_RUN_ID": SCAN_ID,
        "ALLOWED_USER_ID": OWNER_ID,
        "SUPABASE_URL": "https://example.supabase.co",
        "SUPABASE_SECRET_KEY": "sb_secret_private_test_canary",
        "GEMINI_API_KEY": "AIza" + "x" * 35,
    }


class Response:
    def __init__(self, payload, status=200):
        self.payload = json.dumps(payload).encode()
        self.status = status
        self.read_sizes = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, size):
        self.read_sizes.append(size)
        return self.payload[:size]


def eligible_response():
    return Response([{"id": SCAN_ID, "owner_id": OWNER_ID, "status": "failed"}])


def test_one_conditional_https_patch_and_modern_secret_headers(helper, settings):
    response = eligible_response()
    opener = Mock(return_value=response)
    before = datetime.now(timezone.utc)
    assert helper.fail_queued_scan(environ=settings, http_open=opener) is True
    after = datetime.now(timezone.utc)
    opener.assert_called_once()
    request = opener.call_args.args[0]
    parsed = urlsplit(request.full_url)
    assert parsed.scheme == "https"
    assert parsed.netloc == "example.supabase.co"
    assert parsed.path == "/rest/v1/scan_runs"
    query = parse_qs(parsed.query)
    assert query["id"] == [f"eq.{SCAN_ID}"]
    assert query["owner_id"] == [f"eq.{OWNER_ID}"]
    assert query["status"] == ["eq.queued"]
    assert query["select"] == ["id,owner_id,status"]
    assert request.get_method() == "PATCH"
    headers = {name.lower(): value for name, value in request.header_items()}
    assert headers["apikey"] == settings["SUPABASE_SECRET_KEY"]
    assert "authorization" not in headers
    assert headers["prefer"] == "return=representation"
    assert headers["content-type"] == "application/json"
    payload = json.loads(request.data)
    assert set(payload) == {"status", "safe_error", "completed_at"}
    assert payload["status"] == "failed"
    assert payload["safe_error"] == helper.SAFE_SETUP_ERROR
    completion = datetime.fromisoformat(payload["completed_at"])
    assert completion.utcoffset().total_seconds() == 0
    assert before <= completion <= after
    assert opener.call_args.kwargs == {"timeout": 10}
    assert response.read_sizes == [65537]


@pytest.mark.parametrize("winner", ["scanning", "evaluating", "saving", "completed", "failed"])
def test_race_loser_empty_representation_never_retries_or_falls_back(helper, settings, winner):
    # Database owner/id/queued predicates leave every running/terminal winner alone.
    def conditional_patch(request, *, timeout):
        query = parse_qs(urlsplit(request.full_url).query)
        assert query["status"] == ["eq.queued"]
        assert query["id"] == [f"eq.{SCAN_ID}"]
        assert query["owner_id"] == [f"eq.{OWNER_ID}"]
        assert winner != "queued"
        return Response([])
    opener = Mock(side_effect=conditional_patch)
    assert helper.fail_queued_scan(environ=settings, http_open=opener) is False
    opener.assert_called_once()


@pytest.mark.parametrize("name", ["SCAN_RUN_ID", "ALLOWED_USER_ID"])
@pytest.mark.parametrize("value", [None, "", "not-a-uuid", "{00000000-0000-4000-8000-000000000001}", "00000000000040008000000000000001", "x&owner_id=neq.x"])
def test_invalid_identity_never_uses_http(helper, settings, name, value, capsys):
    if value is None:
        settings.pop(name)
    else:
        settings[name] = value
    opener = Mock()
    assert helper.main([], environ=settings, http_open=opener) == 2
    opener.assert_not_called()
    output = capsys.readouterr()
    assert "Traceback" not in output.err
    assert settings["SUPABASE_SECRET_KEY"] not in output.err
    if value and value != "not-a-uuid":
        assert value not in output.err


@pytest.mark.parametrize("url", ["", "http://example.supabase.co", "https://user:pass@example.supabase.co", "https://example.supabase.co@evil.test", "https://example.supabase.co/path", "https://example.supabase.co?apikey=private", "https://example.supabase.co#private", "https://example.supabase.co:8443", "https://127.0.0.1", "https://localhost", "https://example.supabase.co\\@evil.test", "https://example.supabase.co\n"])
def test_unsafe_storage_url_fails_closed_before_http(helper, settings, url, capsys):
    settings["SUPABASE_URL"] = url
    opener = Mock()
    assert helper.main([], environ=settings, http_open=opener) == 2
    opener.assert_not_called()
    assert "private" not in capsys.readouterr().err


@pytest.mark.parametrize("key", ["", "sb_publishable_public", "sb_secret_x\r\nAuthorization: private", "sb_secret_x y", "opaque-not-a-service-key"])
def test_invalid_secret_does_not_enter_headers(helper, settings, key, capsys):
    settings["SUPABASE_SECRET_KEY"] = key
    opener = Mock()
    assert helper.main([], environ=settings, http_open=opener) == 2
    opener.assert_not_called()
    assert "private" not in capsys.readouterr().err


def test_legacy_service_role_jwt_has_bearer_compatibility(helper, settings):
    def part(value):
        return base64.urlsafe_b64encode(json.dumps(value).encode()).decode().rstrip("=")
    settings["SUPABASE_SECRET_KEY"] = f"{part({'alg': 'HS256'})}.{part({'role': 'service_role'})}.testsignature"
    opener = Mock(return_value=eligible_response())
    assert helper.fail_queued_scan(environ=settings, http_open=opener)
    headers = {name.lower(): value for name, value in opener.call_args.args[0].header_items()}
    assert headers["authorization"] == f"Bearer {settings['SUPABASE_SECRET_KEY']}"
    assert headers["apikey"] == settings["SUPABASE_SECRET_KEY"]


def test_legacy_anon_role_is_rejected_before_http(helper, settings, capsys):
    def part(value):
        return base64.urlsafe_b64encode(json.dumps(value).encode()).decode().rstrip("=")
    settings["SUPABASE_SECRET_KEY"] = f"{part({'alg': 'HS256'})}.{part({'role': 'anon'})}.testsignature"
    opener = Mock()
    assert helper.main([], environ=settings, http_open=opener) == 2
    opener.assert_not_called()
    assert settings["SUPABASE_SECRET_KEY"] not in str(capsys.readouterr())


def test_validation_requires_gemini_but_finalization_does_not(helper, settings, capsys):
    settings.pop("GEMINI_API_KEY")
    opener = Mock(return_value=eligible_response())
    assert helper.main(["--validate-only"], environ=settings, http_open=opener) == 2
    opener.assert_not_called()
    assert helper.main([], environ=settings, http_open=opener) == 0
    opener.assert_called_once()
    assert settings["SUPABASE_SECRET_KEY"] not in str(capsys.readouterr())


@pytest.mark.parametrize("gemini", ["", " ", "private\nheader", "private key"])
def test_malformed_gemini_configuration_never_uses_http(helper, settings, gemini, capsys):
    settings["GEMINI_API_KEY"] = gemini
    opener = Mock()
    assert helper.main(["--validate-only"], environ=settings, http_open=opener) == 2
    opener.assert_not_called()
    assert "private" not in capsys.readouterr().err


def test_valid_configuration_has_no_outbound_request_or_secret_output(helper, settings, capsys):
    opener = Mock()
    settings["SCAN_RUN_ID"] = f" {SCAN_ID.upper()} "
    settings["ALLOWED_USER_ID"] = f" {OWNER_ID.upper()} "
    settings["SUPABASE_URL"] += "/"
    assert helper.main(["--validate-only"], environ=settings, http_open=opener) == 0
    opener.assert_not_called()
    assert "canary" not in str(capsys.readouterr())


@pytest.mark.parametrize("error", [URLError("sb_secret_private_test_canary provider body"), TimeoutError("private timeout"), HTTPError("https://private.example", 403, "private denial", {}, None), RuntimeError("private unexpected")])
def test_http_failure_is_safe_and_not_retried(helper, settings, error, capsys):
    opener = Mock(side_effect=error)
    assert helper.main([], environ=settings, http_open=opener) == 1
    opener.assert_called_once()
    output = str(capsys.readouterr())
    assert "private" not in output
    assert "Traceback" not in output


@pytest.mark.parametrize("payload", [None, {}, [{"id": SCAN_ID, "owner_id": OTHER_ID, "status": "failed"}], [{"id": OTHER_ID, "owner_id": OWNER_ID, "status": "failed"}], [{"id": SCAN_ID, "owner_id": OWNER_ID, "status": "scanning"}], [{"id": SCAN_ID}], [{"id": SCAN_ID, "owner_id": OWNER_ID, "status": "failed"}] * 2])
def test_malformed_update_representation_is_safe_without_second_write(helper, settings, payload, capsys):
    opener = Mock(return_value=Response(payload))
    assert helper.main([], environ=settings, http_open=opener) == 1
    opener.assert_called_once()
    assert OTHER_ID not in str(capsys.readouterr())


def test_invalid_json_or_oversized_body_is_not_logged(helper, settings, capsys):
    for body in [b"private-not-json", b"private" * 12000]:
        response = Response(None)
        response.payload = body
        opener = Mock(return_value=response)
        assert helper.main([], environ=settings, http_open=opener) == 1
        opener.assert_called_once()
        assert "private" not in str(capsys.readouterr())


def test_redirect_handler_refuses_following_credentialed_request(helper):
    handler = helper.NoRedirectHandler()
    assert handler.redirect_request(Mock(), Mock(), 302, "redirect", {}, "https://evil.test") is None


@pytest.mark.parametrize("status", [201, 204, 301, 302, 307, 308, 403, 500])
def test_http_non_success_body_is_not_read_and_never_retried(helper, settings, status, capsys):
    response = Response({"private": settings["SUPABASE_SECRET_KEY"]}, status=status)
    opener = Mock(return_value=response)
    assert helper.main([], environ=settings, http_open=opener) == 1
    opener.assert_called_once()
    assert response.read_sizes == []
    assert "private" not in str(capsys.readouterr())


def test_production_opener_has_explicit_no_redirect_tls_and_no_proxy(helper, settings, monkeypatch):
    opener = Mock()
    opener.open.return_value = eligible_response()
    factory = Mock(return_value=opener)
    monkeypatch.setattr(helper, "build_opener", factory)
    assert helper.fail_queued_scan(environ=settings) is True
    factory.assert_called_once()
    handlers = factory.call_args.args
    assert any(isinstance(handler, helper.NoRedirectHandler) for handler in handlers)
    assert any(isinstance(handler, helper.HTTPSHandler) for handler in handlers)
    proxy = next(handler for handler in handlers if isinstance(handler, helper.ProxyHandler))
    assert proxy.proxies == {}
    opener.open.assert_called_once()


def test_helper_uses_only_standard_library_and_never_loads_dotenv(helper):
    import ast
    imports = []
    tree = ast.parse((ROOT / "scripts" / "fail_queued_scan.py").read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(name.name.split(".")[0] for name in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.append(node.module.split(".")[0])
    assert set(imports) <= sys.stdlib_module_names
    assert "deal_finder" not in imports
