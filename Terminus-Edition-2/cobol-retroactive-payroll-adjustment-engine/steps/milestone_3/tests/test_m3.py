import csv
import os
import subprocess
from pathlib import Path

APP = Path("/app")
DATA = APP / "data"
CFG = APP / "config"
OUT = APP / "out"


def write_psv(path, header, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as h:
        w = csv.writer(h, delimiter="|", lineterminator="\n")
        w.writerow(header)
        w.writerows(rows)


def read_psv(path):
    if not path.exists():
        return []
    with path.open(newline="") as h:
        return list(csv.DictReader(h, delimiter="|"))


def reset():
    OUT.mkdir(exist_ok=True)
    for p in OUT.glob("*"):
        p.unlink()


def run(env=None, ok=True):
    e = os.environ.copy()
    if env:
        e.update(env)
    r = subprocess.run(
        ["/app/scripts/run_batch.sh"],
        cwd=APP,
        env=e,
        text=True,
        capture_output=True,
        timeout=60,
    )
    if ok and r.returncode != 0:
        raise AssertionError(r.stdout + r.stderr)
    if not ok and r.returncode == 0:
        raise AssertionError("expected non-zero")
    return r


def fixture():
    reset()
    write_psv(
        CFG / "tax_rules.psv",
        ["from_cents", "to_cents", "rate_bp"],
        [["0", "50000", "1000"], ["50000", "999999999", "2000"]],
    )
    write_psv(
        CFG / "deduction_caps.psv",
        ["employee_id", "cap_cents"],
        [["EMP-A", "2500"], ["EMP-B", "5000"], ["EMP-C", "1000"], ["EMP-D", "5000"]],
    )
    write_psv(
        DATA / "employees.psv",
        ["employee_id", "name", "status"],
        [
            ["EMP-A", "Asha", "ACTIVE"],
            ["EMP-B", "Ben", "ACTIVE"],
            ["EMP-C", "Cory", "ACTIVE"],
            ["EMP-D", "Dina", "ACTIVE"],
        ],
    )
    write_psv(
        DATA / "compensation_history.psv",
        [
            "employee_id",
            "effective_from",
            "base_cents",
            "allowance_cents",
            "overtime_rate_bp",
        ],
        [
            ["EMP-A", "202601", "40000", "5000", "1500"],
            ["EMP-A", "202604", "45000", "7000", "1500"],
            ["EMP-B", "202601", "60000", "6000", "1250"],
            ["EMP-C", "202602", "55000", "5000", "1000"],
        ],
    )
    write_psv(
        DATA / "prior_payroll.psv",
        [
            "employee_id",
            "period",
            "gross_cents",
            "tax_cents",
            "deduction_cents",
            "overtime_hours",
        ],
        [
            ["EMP-A", "202602", "45000", "4500", "2000", "0"],
            ["EMP-A", "202604", "52000", "5400", "2300", "0"],
            ["EMP-B", "202603", "67500", "8500", "3000", "2"],
            ["EMP-D", "202602", "10000", "1000", "500", "0"],
        ],
    )
    write_psv(
        DATA / "prior_adjustment_ledger.psv",
        [
            "adjustment_id",
            "employee_id",
            "period",
            "gross_delta_cents",
            "tax_delta_cents",
            "deduction_delta_cents",
            "net_delta_cents",
            "status",
        ],
        [],
    )


class TestMilestone3:
    """Tax and deduction deltas must be derived from retro deltas and caps."""

    def test_tax_delta_uses_retro_delta_not_corrected_total(self):
        fixture()
        run()
        row = {
            (r["employee_id"], r["period"]): r
            for r in read_psv(OUT / "tax_delta_report.psv")
        }[("EMP-B", "202603")]
        assert row["gross_delta_cents"] == "13500"
        assert row["tax_delta_cents"] == "1350"

    def test_deduction_delta_respects_remaining_cap(self):
        fixture()
        run()
        row = {
            (r["employee_id"], r["period"]): r
            for r in read_psv(OUT / "tax_delta_report.psv")
        }[("EMP-B", "202603")]
        assert row["deduction_delta_cents"] == "675"
        totals = {r["metric"]: r["value"] for r in read_psv(OUT / "control_totals.psv")}
        assert totals["gross_delta_cents"] == "13500"
