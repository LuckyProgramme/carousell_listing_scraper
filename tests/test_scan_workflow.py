"""Static safety contracts for the manual-only scan workflow."""

from itertools import product
from pathlib import Path
import re

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[1]
CHECKOUT_PIN = "actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1"
UV_PIN = "astral-sh/setup-uv@c18668ad3cf93ea998bef934396af7bb5c839dc7"


@pytest.fixture
def workflow():
    path = ROOT / ".github" / "workflows" / "scan.yml"
    assert path.exists(), "The manual scan workflow is missing."
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def steps_by_id(workflow):
    return {step["id"]: step for step in workflow["jobs"]["scan"]["steps"]}


def test_only_manual_trigger_and_required_scan_input(workflow):
    assert set(workflow["on"]) == {"workflow_dispatch"}
    inputs = workflow["on"]["workflow_dispatch"]["inputs"]
    assert set(inputs) == {"scan_run_id"}
    assert inputs["scan_run_id"]["type"] == "string"
    assert inputs["scan_run_id"]["required"] is True
    assert "${{ inputs.scan_run_id }}" in workflow["run-name"]


def test_minimal_permissions_and_repository_wide_concurrency(workflow):
    assert workflow["permissions"] == {"contents": "read"}
    group = workflow["concurrency"]["group"]
    assert group == "deal-finder-scan"
    assert "${{" not in group
    assert workflow["concurrency"]["cancel-in-progress"] is False
    assert set(workflow["jobs"]) == {"scan"}
    assert workflow["jobs"]["scan"]["runs-on"] == "ubuntu-24.04"


def test_verified_pins_and_no_persisted_credentials_or_cache_uploads(workflow):
    steps = steps_by_id(workflow)
    assert steps["checkout"]["uses"] == CHECKOUT_PIN
    assert steps["checkout"]["with"]["persist-credentials"] is False
    assert steps["setup_uv"]["uses"] == UV_PIN
    settings = steps["setup_uv"]["with"]
    assert settings["version"] == "0.11.24"
    for key in ["enable-cache", "restore-cache", "save-cache", "cache-python"]:
        assert settings[key] in (False, "false")
    for step in steps.values():
        if "uses" in step:
            assert re.fullmatch(r"[\w-]+/[\w-]+@[0-9a-f]{40}", step["uses"])


def test_locked_editable_python_install_then_single_worker(workflow):
    steps = steps_by_id(workflow)
    assert steps["install_python"]["run"] == "uv python install 3.12"
    assert steps["install_dependencies"]["run"] == "uv sync --locked --no-dev --python 3.12"
    assert steps["worker"]["run"] == ".venv/bin/python -m deal_finder.scan_job"
    runs = "\n".join(step.get("run", "") for step in steps.values())
    assert runs.count("-m deal_finder.scan_job") == 1
    assert "--frozen" not in runs
    assert "--no-editable" not in runs
    ids = list(steps)
    assert ids.index("validate_config") < ids.index("worker")
    assert ids.index("install_dependencies") < ids.index("worker")


def test_inputs_and_secrets_are_scoped_to_needed_steps_only(workflow):
    assert "env" not in workflow
    assert "env" not in workflow["jobs"]["scan"]
    steps = steps_by_id(workflow)
    expected_env = {
        "SCAN_RUN_ID": "${{ inputs.scan_run_id }}",
        "ALLOWED_USER_ID": "${{ secrets.ALLOWED_USER_ID }}",
        "SUPABASE_URL": "${{ secrets.SUPABASE_URL }}",
        "SUPABASE_SECRET_KEY": "${{ secrets.SUPABASE_SECRET_KEY }}",
    }
    for name in ["validate_config", "worker", "finalize_setup_failure"]:
        expected = dict(expected_env)
        if name != "finalize_setup_failure":
            expected["GEMINI_API_KEY"] = "${{ secrets.GEMINI_API_KEY }}"
        assert steps[name]["env"] == expected
    for name in ["checkout", "setup_uv", "install_python", "install_dependencies"]:
        assert "env" not in steps[name]
    for step in steps.values():
        assert "${{" not in step.get("run", "")
    assert steps["validate_config"]["run"] == "python3 scripts/fail_queued_scan.py --validate-only"
    assert steps["finalize_setup_failure"]["run"] == "python3 scripts/fail_queued_scan.py"


def test_finalizer_exact_status_condition_matches_failure_truth_table(workflow):
    expression = steps_by_id(workflow)["finalize_setup_failure"]["if"]
    expected = "failure() && !cancelled() && steps.checkout.outcome == 'success' && steps.worker.outcome == 'skipped' && (steps.validate_config.outcome == 'failure' || steps.setup_uv.outcome == 'failure' || steps.install_python.outcome == 'failure' || steps.install_dependencies.outcome == 'failure')"
    assert " ".join(expression.removeprefix("${{").removesuffix("}}").split()) == expected
    # Independently evaluate the actual restricted expression with representative
    # previous step outcomes. Worker failures/claim losses/cancellation never run it.
    setup_names = ["validate_config", "setup_uv", "install_python", "install_dependencies"]
    for checkout, worker, setup_index, cancelled in product(["success", "failure", "skipped"], ["success", "failure", "skipped"], range(5), [False, True]):
        outcomes = {"checkout": checkout, "worker": worker}
        outcomes.update({name: "failure" if index == setup_index else "success" for index, name in enumerate(setup_names)})
        failed = "failure" in outcomes.values()
        actual = expression.removeprefix("${{").removesuffix("}}").strip()
        actual = actual.replace("failure()", str(failed)).replace("!cancelled()", str(not cancelled))
        actual = re.sub(r"steps\.(\w+)\.outcome", lambda match: repr(outcomes[match[1]]), actual)
        actual = actual.replace("&&", " and ").replace("||", " or ")
        should_run = checkout == "success" and worker == "skipped" and setup_index < 4 and not cancelled
        assert eval(actual, {"__builtins__": {}}) is should_run


def test_no_application_timeout_retry_schedule_or_artifact(workflow):
    def keys(value):
        if isinstance(value, dict):
            for key, child in value.items():
                yield key
                yield from keys(child)
        elif isinstance(value, list):
            for child in value:
                yield from keys(child)
    assert not set(keys(workflow)) & {"timeout-minutes", "schedule", "continue-on-error", "strategy"}
    source = (ROOT / ".github" / "workflows" / "scan.yml").read_text()
    assert "upload-artifact" not in source
    assert "actions/cache" not in source
    assert "retry" not in source.lower()
