"""Verifier tests for workload manifest alias normalization."""

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


def test_m2():
    RULES.write_text(
        "\n".join(
            [
                "DCL ELIGIBLE_STATE CHAR(12) INIT('LIVE');",
                "DCL OPEN_ROLLOUT_STATE CHAR(8) INIT('OPEN');",
                "DCL REASON_1 CHAR(12) INIT('GO');",
                "DCL REASON_2 CHAR(12) INIT('CHK');",
                "DCL REASON_3 CHAR(12) INIT('WAIT');",
                "DCL ALIAS_1 CHAR(20) INIT('f=>FED');",
                "DCL ALIAS_2 CHAR(20) INIT('a=>ACH');",
                "DCL ALIAS_3 CHAR(20) INIT('s=>SWIFT');",
            ]
        )
        + "\n"
    )
    write_psv(
        MANIFESTS,
        ["workload_id", "namespace", "selector_label", "port_name", "probe_path", "applied_ts", "state", "kind_code"],
        [["R-9", "991100", "99", "f", "NYC", "20260612120000", "LIVE", "tm"]],
    )
    write_psv(
        CHECKS,
        ["claim_id", "workload_id", "namespace", "selector_label", "port_name", "check_ts", "check_code", "probe_path"],
        [["C9", "R-9", "991100", "99", "FED", "20260612120500", "go", "NYC"]],
    )
    write_psv(WINDOWS, ["namespace", "open_ts", "close_ts", "state"], [["991100", "20260612115900", "20260612123000", "OPEN"]])
    REPORT.parent.mkdir(exist_ok=True)
    rows = run_program()
    assert rows[0]["status"] == "CONSISTENT"
    assert rows[0]["port_name"] == "FED"
