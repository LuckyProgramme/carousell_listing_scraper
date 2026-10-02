"""Runner boundary tests use fake configuration and never contact providers."""

from unittest.mock import Mock
import os
from pathlib import Path
import subprocess
import sys

import pytest

from deal_finder import scan_job
from deal_finder.models import ScanRun
from deal_finder.repository import RepositoryError
from deal_finder.scan_service import run_repository_scan

SCAN_ID = "11111111-1111-4111-8111-111111111111"
OWNER_ID = "749743db-c366-47c9-9373-bec966857b32"
OTHER_OWNER = "22222222-2222-4222-8222-222222222222"


@pytest.fixture
def runner(monkeypatch):
    monkeypatch.setenv("SCAN_RUN_ID", SCAN_ID)
    monkeypatch.setenv("ALLOWED_USER_ID", OWNER_ID)
    monkeypatch.setattr(scan_job, "configure_logging", Mock())
    repository = Mock()
    factory = Mock(return_value=repository)
    monkeypatch.setattr(scan_job.SupabaseRepository, "from_env", factory)
    return repository, factory


@pytest.mark.parametrize("name", ["SCAN_RUN_ID", "ALLOWED_USER_ID"])
@pytest.mark.parametrize("value", [None, "", "not-a-uuid", "x&status=eq.scanning", "11111111111141118111111111111111", "{11111111-1111-4111-8111-111111111111}"])
def test_invalid_or_missing_ids_stop_before_repository_creation(monkeypatch, runner, capsys, caplog, name, value):
    _, factory = runner
    if value is None:
        monkeypatch.delenv(name)
    else:
        monkeypatch.setenv(name, value)
    assert scan_job.main() == 2
    factory.assert_not_called()
    output = capsys.readouterr()
    assert "Cloud Run" not in output.out + output.err + caplog.text
    if value:
        assert value not in output.out + output.err + caplog.text


def test_success_forwards_normalized_scan_and_allowed_owner(monkeypatch, runner, capsys):
    repository, factory = runner
    monkeypatch.setenv("SCAN_RUN_ID", f" {SCAN_ID.upper()} ")
    monkeypatch.setenv("ALLOWED_USER_ID", f" {OWNER_ID.upper()} ")
    execute = Mock(return_value=ScanRun(SCAN_ID, OWNER_ID, "completed", listings_count=3, candidates_count=2, deals_count=1))
    monkeypatch.setattr(scan_job, "run_repository_scan", execute)
    assert scan_job.main() == 0
    factory.assert_called_once()
    execute.assert_called_once_with(repository, SCAN_ID, expected_owner_id=OWNER_ID)
    assert "listings=3 candidates=2 deals=1" in capsys.readouterr().out


@pytest.mark.parametrize("error", [RepositoryError("sb_secret_private_canary provider body"), ValueError("private malformed configuration"), RuntimeError("private unexpected failure")])
def test_failure_prints_only_safe_errors(monkeypatch, runner, capsys, caplog, error):
    _, factory = runner
    factory.side_effect = error
    assert scan_job.main() != 0
    output = capsys.readouterr()
    assert "private" not in output.out + output.err + caplog.text
    assert "Traceback" not in output.out + output.err + caplog.text


@pytest.mark.parametrize("status", ["scanning", "evaluating", "saving", "completed", "failed"])
def test_rerun_uses_actual_service_and_exits_without_work(monkeypatch, runner, capsys, status):
    repository, _ = runner
    repository.get_scan.return_value = ScanRun(SCAN_ID, OWNER_ID, status)
    scraper, gemini = Mock(), Mock()
    def execute(repository, scan_id, **kwargs):
        return run_repository_scan(repository, scan_id, scrape_targets=scraper, run_cascade=gemini, **kwargs)
    monkeypatch.setattr(scan_job, "run_repository_scan", execute)
    assert scan_job.main() == 0
    repository.get_scan.assert_called_once_with(SCAN_ID, OWNER_ID)
    repository.list_enabled_targets.assert_not_called()
    repository.claim_queued_scan.assert_not_called()
    repository.fail_queued_scan.assert_not_called()
    repository.update_scan.assert_not_called()
    scraper.assert_not_called()
    gemini.assert_not_called()
    assert "completed:" not in capsys.readouterr().out


def test_wrong_owner_returned_by_storage_cannot_reach_targets_or_scraper(monkeypatch, runner, capsys, caplog):
    repository, _ = runner
    repository.get_scan.return_value = ScanRun(SCAN_ID, OTHER_OWNER, "queued")
    scraper, gemini = Mock(), Mock()
    def execute(repository, scan_id, **kwargs):
        return run_repository_scan(repository, scan_id, scrape_targets=scraper, run_cascade=gemini, **kwargs)
    monkeypatch.setattr(scan_job, "run_repository_scan", execute)
    assert scan_job.main() != 0
    repository.get_scan.assert_called_once_with(SCAN_ID, OWNER_ID)
    repository.list_enabled_targets.assert_not_called()
    repository.claim_queued_scan.assert_not_called()
    repository.fail_queued_scan.assert_not_called()
    repository.update_scan.assert_not_called()
    scraper.assert_not_called()
    gemini.assert_not_called()
    output = capsys.readouterr()
    assert OTHER_OWNER not in output.out + output.err + caplog.text


@pytest.mark.parametrize("scan_id,code", [(SCAN_ID, 1), ("invalid-private-canary", 2)])
def test_real_entry_point_keeps_import_time_configuration_failures_safe(scan_id, code):
    # Invalid numeric configuration previously crashed during module import,
    # before main's validation or safe exception handling could execute.
    environment = dict(os.environ)
    environment.update({
        "SCAN_RUN_ID": scan_id,
        "ALLOWED_USER_ID": OWNER_ID,
        "GEMINI_AUDIT_CHUNK_SIZE": "private-import-canary",
        "GEMINI_API_KEY": "",
        "SUPABASE_URL": "https://example.supabase.co",
        "SUPABASE_SECRET_KEY": "sb_secret_offline_example",
    })
    result = subprocess.run(
        [sys.executable, "-m", "deal_finder.scan_job"],
        cwd=Path(__file__).resolve().parents[1], env=environment,
        capture_output=True, text=True, timeout=15, check=False,
    )
    assert result.returncode == code
    assert "private" not in result.stdout + result.stderr
    assert "Traceback" not in result.stdout + result.stderr
