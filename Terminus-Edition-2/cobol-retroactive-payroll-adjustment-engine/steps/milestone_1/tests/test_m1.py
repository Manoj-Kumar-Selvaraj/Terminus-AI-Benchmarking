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


class TestMilestone1:
    """Effective-dated compensation must be resolved per historical period."""

    def test_period_uses_applicable_compensation_not_newest(self):
        fixture()
        run()
        rows = {
            (r["employee_id"], r["period"]): r
            for r in read_psv(OUT / "period_delta_report.psv")
        }
        assert ("EMP-A", "202604") not in rows or rows[("EMP-A", "202604")][
            "gross_delta_cents"
        ] == "0"
        ledger = {
            (r["employee_id"], r["period"]): r
            for r in read_psv(OUT / "adjustment_ledger.psv")
        }
        assert ("EMP-A", "202602") not in ledger, (
            "old newest-row bug creates a false historical adjustment"
        )
        assert ledger[("EMP-B", "202603")]["gross_delta_cents"] == "13500"
        assert ledger[("EMP-B", "202603")]["adjustment_id"] == "ADJ-EMP-B-202603"
        assert rows[("EMP-B", "202603")]["corrected_gross_cents"] == "81000"
        assert rows[("EMP-B", "202603")]["gross_delta_cents"] == "13500"

    def test_prior_payroll_files_remain_immutable(self):
        """Evidence inputs must not be rewritten in place."""
        fixture()
        before_payroll = (DATA / "prior_payroll.psv").read_text()
        before_comp = (DATA / "compensation_history.psv").read_text()
        run()
        assert (DATA / "prior_payroll.psv").read_text() == before_payroll
        assert (DATA / "compensation_history.psv").read_text() == before_comp

    def test_missing_effective_compensation_rejects_without_adjustment(self):
        fixture()
        run()
        rejects = {
            (r["employee_id"], r["period"]): r["reason_code"]
            for r in read_psv(OUT / "reject_ledger.psv")
        }
        assert rejects[("EMP-D", "202602")] == "COMPENSATION_RULE_MISSING"

    def test_positive_delta_is_computed_for_new_employee_fixture(self):
        """A valid historical correction must create an adjustment, not only suppress false positives."""
        fixture()
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
                ["EMP-C", "202602", "50000", "5000", "500", "0"],
                ["EMP-D", "202602", "10000", "1000", "500", "0"],
            ],
        )
        run()
        ledger = {
            (r["employee_id"], r["period"]): r
            for r in read_psv(OUT / "adjustment_ledger.psv")
        }
        assert ledger[("EMP-C", "202602")]["gross_delta_cents"] == "10000"
        rejects = {
            (r["employee_id"], r["period"]): r["reason_code"]
            for r in read_psv(OUT / "reject_ledger.psv")
        }
        assert rejects[("EMP-D", "202602")] == "COMPENSATION_RULE_MISSING"
