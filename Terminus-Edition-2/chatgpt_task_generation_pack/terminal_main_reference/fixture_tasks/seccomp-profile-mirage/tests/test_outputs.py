"""Black-box verifier for /app/output/report.json augmented by Rust integration tests.

Rust tests (cargo test under /app) exercise routing/bind/report gates against inline ScenarioSpec literals,
so regressions cannot be fixed solely by echoing bundled JSON fixtures in Python assertions.
"""

import json
import shutil
import subprocess
from pathlib import Path

import pytest


RUNTIME_TOML = Path("/app/config/runtime.toml")
# Written only inside the verifier container; never shipped in the task zip.
DYNAMIC_SCENARIO_PATH = Path("/app/data/scenarios/_verifier_dynamic_probe.json")


def _cargo_executable() -> str:
    """Resolve cargo; verifier may run with a PATH that omits the Rust toolchain."""
    exe = shutil.which("cargo")
    if exe:
        return exe
    for line in RUNTIME_TOML.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith("verifier_cargo_bin = "):
            return line.split("=", 1)[1].strip().strip('"')
    raise RuntimeError("cargo executable not found (PATH and runtime.toml)")


REPORT_PATH = Path("/app/output/report.json")
APP_DIR = Path("/app")
SCENARIOS_DIR = Path("/app/data/scenarios")
ROW_KEYS = {
    "scenario",
    "selected_tag",
    "attached_tag",
    "declared_tag",
    "declared_allows_op",
    "effective_blocked_op",
    "compliant",
    "reason",
}


def _load_scenarios():
    scenarios = {}
    for item in sorted(SCENARIOS_DIR.glob("*.json")):
        doc = json.loads(item.read_text())
        scenarios[doc["scenario"]] = doc
    return scenarios


def _expected_selected(spec):
    if spec["retry_count"] > 0 and spec["prefer_alt"]:
        return spec["fallback_tag"]
    return spec["primary_tag"]


def _expected_blocked(spec, attached_tag):
    if attached_tag == spec["primary_tag"]:
        return spec["runtime_denies_primary"]
    if attached_tag == spec["fallback_tag"]:
        return spec["runtime_denies_fallback"]
    return False


def _verifier_dynamic_scenario():
    """Scenario unknown at agent image build time; blocks a six-row hardcoded report."""
    return {
        "scenario": "verifier_dynamic_probe",
        "primary_tag": "dyn_m9_primary",
        "fallback_tag": "dyn_m9_fallback",
        "declared_tag": "dyn_m9_primary",
        "retry_count": 2,
        "prefer_alt": True,
        "op_name": "landlock",
        "declared_allows_op": True,
        "runtime_denies_primary": True,
        "runtime_denies_fallback": False,
    }


@pytest.fixture(scope="module", autouse=True)
def rust_integration_suite_guard():
    """Run crate integration tests before pytest exercises /app/output/report.json."""
    subprocess.run(
        [_cargo_executable(), "test", "--quiet", "--locked"],
        cwd=APP_DIR,
        check=True,
        text=True,
    )


@pytest.fixture(scope="module")
def payload():
    DYNAMIC_SCENARIO_PATH.write_text(
        json.dumps(_verifier_dynamic_scenario(), indent=2) + "\n",
        encoding="utf-8",
    )
    if REPORT_PATH.exists():
        REPORT_PATH.unlink()
    subprocess.run(
        [_cargo_executable(), "run", "--quiet", "--locked"],
        cwd=APP_DIR,
        check=True,
        text=True,
    )
    assert REPORT_PATH.exists(), "expected /app/output/report.json to be written"
    try:
        yield json.loads(REPORT_PATH.read_text())
    finally:
        if DYNAMIC_SCENARIO_PATH.exists():
            DYNAMIC_SCENARIO_PATH.unlink()


def rows_by_name(report):
    return {row["scenario"]: row for row in report["run_report"]}


def test_top_level_schema_is_exact(payload):
    """Report shape is constrained to exactly run_report and summary."""
    assert set(payload.keys()) == {"run_report", "summary"}
    assert isinstance(payload["run_report"], list)
    assert isinstance(payload["summary"], dict)
    assert set(payload["summary"].keys()) == {"compliant_count", "total"}


def test_run_report_rows_are_sorted_by_scenario_name(payload):
    """Rows must be deterministic and ordered by scenario name."""
    names = [row["scenario"] for row in payload["run_report"]]
    assert names == sorted(names)


def test_row_schema_and_runtime_attachment_alignment(payload):
    """Each row keeps required keys and runtime attach equals selected tag."""
    for row in payload["run_report"]:
        assert set(row.keys()) == ROW_KEYS
        assert row["attached_tag"] == row["selected_tag"]


def test_report_fields_match_scenario_ground_truth(payload):
    """Scenario-driven fields in each row must match the spec files on disk."""
    scenarios = _load_scenarios()
    rows = rows_by_name(payload)
    assert set(rows.keys()) == set(scenarios.keys())
    for name, row in rows.items():
        spec = scenarios[name]
        assert row["declared_tag"] == spec["declared_tag"]
        assert row["declared_allows_op"] == spec["declared_allows_op"]
        expected_selected = _expected_selected(spec)
        assert row["selected_tag"] == expected_selected
        expected_blocked = _expected_blocked(spec, row["attached_tag"])
        assert row["effective_blocked_op"] == expected_blocked


def test_derived_compliance_posture_matches_intended_truth(payload):
    """Each row's compliant flag matches policy when routing and bind behave as specified."""
    scenarios = _load_scenarios()
    rows = rows_by_name(payload)
    assert set(rows.keys()) == set(scenarios.keys())
    for name, spec in scenarios.items():
        row = rows[name]
        sel = _expected_selected(spec)
        intended_attached = sel
        blocked_if_intended = _expected_blocked(spec, intended_attached)
        expect_ok = (spec["declared_tag"] == intended_attached) and (
            spec["declared_allows_op"] == (not blocked_if_intended)
        )
        assert row["compliant"] == expect_ok


def test_non_compliant_rows_have_drift_reason(payload):
    """Non-compliant rows cite drift with a real explanation; compliant rows stay separate."""
    for row in payload["run_report"]:
        reason = row["reason"].strip()
        assert reason, "every row must carry a non-empty reason"
        low = reason.lower()
        if row["compliant"]:
            assert "drift" not in low, "compliant rows must not use drift wording in reason"
        else:
            assert "drift" in low
            assert len(reason) >= 8, "non-compliant drift reasons must be substantive, not a bare token"


def test_compliance_logic_and_summary_counts(payload):
    """Summary and compliant flags must match declaration-vs-runtime equivalence."""
    computed_ok = 0
    for row in payload["run_report"]:
        should_be_ok = (row["declared_tag"] == row["attached_tag"]) and (
            row["declared_allows_op"] == (not row["effective_blocked_op"])
        )
        assert row["compliant"] == should_be_ok
        if row["compliant"]:
            computed_ok += 1
    assert payload["summary"]["compliant_count"] == computed_ok
    assert payload["summary"]["total"] == len(payload["run_report"])
