"""Verifier tests for rollout window gating."""

import csv
import subprocess
from pathlib import Path

APP = Path("/app")
MANIFESTS = APP / "data/manifests.psv"
CHECKS = APP / "data/rollout_checks.psv"
WINDOWS = APP / "config/rollout_windows.psv"
RULES = APP / "src/manifest_rules.pli"
REPORT = APP / "out/manifest_report.csv"


def write_psv(path, header, rows):
    path.write_text("|".join(header) + "\n" + "\n".join("|".join(r) for r in rows) + "\n")


def run_program():
    subprocess.run(["/app/scripts/run_batch.sh"], check=True, cwd=APP, timeout=60)
    with REPORT.open(newline="") as f:
        return list(csv.DictReader(f, delimiter="|"))


def test_m3():
    RULES.write_text(
        "\n".join(
            [
                "DCL ELIGIBLE_STATE CHAR(12) INIT('OPEN');",
                "DCL OPEN_ROLLOUT_STATE CHAR(8) INIT('OPEN');",
                "DCL REASON_1 CHAR(12) INIT('OK');",
                "DCL REASON_2 CHAR(12) INIT('WATCH');",
                "DCL REASON_3 CHAR(12) INIT('DONE');",
                "DCL ALIAS_1 CHAR(20) INIT('8080=>HTTP');",
                "DCL ALIAS_2 CHAR(20) INIT('A=>ACH');",
                "DCL ALIAS_3 CHAR(20) INIT('S=>SWIFT');",
            ]
        )
        + "\n"
    )
    write_psv(
        MANIFESTS,
        ["workload_id", "namespace", "selector_label", "port_name", "probe_path", "applied_ts", "state", "kind_code"],
        [
            ["R-A", "991100", "10", "FED", "NYC", "20260612120000", "OPEN", "TM"],
            ["R-A", "991100", "10", "FED", "NYC", "20260612120100", "OPEN", "TM"],
        ],
    )
    write_psv(
        CHECKS,
        ["claim_id", "workload_id", "namespace", "selector_label", "port_name", "check_ts", "check_code", "probe_path"],
        [["C-W", "R-A", "991100", "10", "FED", "20260612120500", "OK", "NYC"]],
    )
    write_psv(WINDOWS, ["namespace", "open_ts", "close_ts", "state"], [["991100", "20260612115900", "20260612123000", "OPEN"]])
    REPORT.parent.mkdir(exist_ok=True)
    assert run_program()[0]["status"] == "CONSISTENT"
    write_psv(
        CHECKS,
        ["claim_id", "workload_id", "namespace", "selector_label", "port_name", "check_ts", "check_code", "probe_path"],
        [["C-X", "R-A", "991100", "10", "FED", "20260612130000", "OK", "NYC"]],
    )
    assert run_program()[0]["status"] == "DRIFTED"
