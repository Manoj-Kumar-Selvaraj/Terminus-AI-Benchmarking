"""Verifier tests for hospital compliance, low-value padding, and OFAC controls."""

import csv
import subprocess
from pathlib import Path


APP = Path("/app")
SRC = APP / "src" / "claim_denial_reconcile.cbl"
BIN = APP / "build" / "claim_denial_reconcile"
SOURCE = APP / "data" / "claims.dat"
ACTION = APP / "data" / "denials.dat"
CALENDAR = APP / "config" / "adjudication_calendar.txt"
OFAC = APP / "config" / "ofac_screening.dat"
REPORT = APP / "out" / "denial_report.csv"
SUMMARY = APP / "out" / "denial_summary.txt"
TRACE = APP / "out" / "source_consumption.csv"


def source(record_id, account, service, amount, date, hospital, state, docs="Y", status="A", branch="B001"):
    """Create one compliance-extended fixed-width source record."""
    return (
        f"S{record_id:<12}{account:<8}{service:<3}{amount:010d}{date}"
        f"{status}{branch:<4}{hospital:<5}{state:<2}{docs}"
    )


def denial(record_id, account, service, amount, date, reason, hospital, state, branch="B001"):
    """Create one compliance-extended fixed-width denial record."""
    return (
        f"A{record_id:<12}{account:<8}{service:<3}{amount:010d}{date}"
        f"{reason:<3}{branch:<4}{hospital:<5}{state:<2}"
    )


def ofac(account, hospital, decision, date):
    """Create one fixed-width OFAC screening record."""
    return f"{account:<8}{hospital:<5}{decision:<5}{date}"


def compile_program():
    """Compile the real COBOL program."""
    BIN.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["cobc", "-x", "-free", "-O2", "-o", str(BIN), str(SRC)],
        check=True,
        cwd=APP,
        timeout=60,
    )


def write_inputs(source_lines, denial_lines, calendar_lines, ofac_lines):
    """Write binary-safe runtime fixtures and clear prior outputs."""
    SOURCE.write_bytes(b"\n".join(line.encode("latin-1") for line in source_lines) + b"\n")
    ACTION.write_bytes(b"\n".join(line.encode("latin-1") for line in denial_lines) + b"\n")
    CALENDAR.write_bytes(b"\n".join(line.encode("latin-1") for line in calendar_lines) + b"\n")
    OFAC.write_bytes(b"\n".join(line.encode("latin-1") for line in ofac_lines) + b"\n")
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.unlink(missing_ok=True)
    SUMMARY.unlink(missing_ok=True)
    TRACE.unlink(missing_ok=True)


def run_program():
    """Run the reconciler and parse its two output artifacts."""
    subprocess.run([str(BIN)], check=True, cwd=APP, timeout=60)
    report_bytes = REPORT.read_bytes()
    summary_bytes = SUMMARY.read_bytes()
    assert b"\x00" not in report_bytes
    assert b"\x00" not in summary_bytes
    with REPORT.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    summary = {}
    for raw in SUMMARY.read_text().splitlines():
        key, value = raw.split("=", 1)
        summary[key] = int(value)
    return rows, summary


def read_trace():
    """Read the matched-row source consumption trace."""
    with TRACE.open(newline="") as handle:
        return list(csv.DictReader(handle))


class TestMilestone4:
    def test_full_compliance_identity_and_document_gate(self):
        """Hospital, state, and source document approval must independently gate clearing."""
        compile_program()
        write_inputs(
            [
                source("HCCOMP000001", "ACCT1001", "ER", 1000, "20261201", "HSP01", "NY", docs="y", branch="BC01"),
                source("HCCOMP000002", "ACCT1002", "LAB", 2000, "20261201", "HSP02", "CA", branch="BC02"),
                source("HCCOMP000003", "ACCT1003", "IMG", 3000, "20261201", "HSP03", "TX", docs="N", branch="BC03"),
            ],
            [
                denial("HCCOMP000001", "ACCT1001", "E1", 1000, "20261202", "D01", "HSP01", "NY", branch="BC01"),
                denial("HCCOMP000002", "ACCT1002", "LB", 2000, "20261202", "D02", "WRONG", "CA", branch="BC02"),
                denial("HCCOMP000002", "ACCT1002", "LB", 2000, "20261202", "D02", "HSP02", "NV", branch="BC02"),
                denial("HCCOMP000003", "ACCT1003", "XR", 3000, "20261202", "D17", "HSP03", "TX", branch="BC03"),
            ],
            ["20261201=OPEN"],
            [
                ofac("ACCT1001", "HSP01", "CLEAR", "20261202"),
                ofac("ACCT1002", "HSP02", "CLEAR", "20261202"),
                ofac("ACCT1003", "HSP03", "CLEAR", "20261202"),
            ],
        )
        rows, summary = run_program()
        trace_rows = read_trace()

        assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED"]
        assert [row["service"] for row in rows] == ["ER", "", "", ""]
        assert [row["reason"] for row in rows] == ["D01", "D02", "D02", "D17"]
        assert trace_rows == [
            {
                "action_record_id": "HCCOMP000001",
                "source_row": "0001",
                "source_date": "20261201",
            }
        ]
        assert summary == {
            "matched_count": 1,
            "matched_amount_cents": 1000,
            "unmatched_count": 3,
            "unmatched_amount_cents": 7000,
        }

    def test_blank_or_malformed_document_approval_is_ineligible(self):
        """Blank or malformed supporting-document flags must fail closed."""
        compile_program()
        write_inputs(
            [
                source("HCBLANK00001", "ACCT5001", "ER", 500, "20261201", "HB001", "NY", docs=" ", branch="BD01"),
                source("HCMALFORM001", "ACCT5002", "LAB", 600, "20261201", "HB002", "NY", docs="X", branch="BD02"),
            ],
            [
                denial("HCBLANK00001", "ACCT5001", "E1", 500, "20261202", "D01", "HB001", "NY", branch="BD01"),
                denial("HCMALFORM001", "ACCT5002", "LB", 600, "20261202", "D02", "HB002", "NY", branch="BD02"),
            ],
            ["20261201=OPEN"],
            [
                ofac("ACCT5001", "HB001", "CLEAR", "20261202"),
                ofac("ACCT5002", "HB002", "CLEAR", "20261202"),
            ],
        )
        rows, summary = run_program()
        trace_rows = read_trace()

        assert [row["status"] for row in rows] == ["UNMATCHED", "UNMATCHED"]
        assert [row["service"] for row in rows] == ["", ""]
        assert trace_rows == []
        assert summary == {
            "matched_count": 0,
            "matched_amount_cents": 0,
            "unmatched_count": 2,
            "unmatched_amount_cents": 1100,
        }

    def test_low_values_are_text_padding_but_never_numeric_padding(self):
        """Binary low-values should normalize in text fields and invalidate amount or date fields."""
        compile_program()
        nul = "\x00"
        good_source = source("HCNUL1", "A1", "ER", 450, "20261210", "H1001", "IL", branch="BN01")
        good_denial = denial("HCNUL1", "A1", "E1", 450, "20261211", "D01", "H1001", "IL", branch="BN01")
        good_source = good_source.replace("HCNUL1      ", "HCNUL1" + nul * 6).replace("A1      ", "A1" + nul * 6)
        good_denial = good_denial.replace("HCNUL1      ", "HCNUL1" + nul * 6).replace("A1      ", "A1" + nul * 6)
        bad_amount = source("HCNULAMT001", "ACCT2001", "LAB", 500, "20261210", "H2001", "IL", branch="BN02")
        bad_amount = bad_amount[:25] + "00000" + nul + "0500" + bad_amount[35:]
        bad_date = source("HCNULDATE01", "ACCT2002", "IMG", 600, "20261210", "H2002", "IL", branch="BN03")
        bad_date = bad_date[:38] + nul + bad_date[39:]
        write_inputs(
            [good_source, bad_amount, bad_date],
            [
                good_denial,
                denial("HCNULAMT001", "ACCT2001", "LB", 500, "20261211", "D02", "H2001", "IL", branch="BN02"),
                denial("HCNULDATE01", "ACCT2002", "XR", 600, "20261211", "D17", "H2002", "IL", branch="BN03"),
            ],
            ["20261210=OPEN"],
            [
                ofac("A1", "H1001", "clear", "20261211").replace("A1      ", "A1" + nul * 6),
                ofac("ACCT2001", "H2001", "CLEAR", "20261211"),
                ofac("ACCT2002", "H2002", "CLEAR", "20261211"),
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED", "UNMATCHED"]
        assert rows[0]["record_id"] == "HCNUL1"
        assert rows[0]["account"] == "A1"
        assert summary["unmatched_amount_cents"] == 1100

    def test_ofac_low_values_normalize_hospital_and_malformed_decision_fails_closed(self):
        """OFAC text padding applies beyond account, but decisions still must trim to CLEAR."""
        compile_program()
        nul = "\x00"
        write_inputs(
            [
                source("HCOFNULL001", "ACCTX001", "ER", 710, "20261210", "H1", "IL", branch="BX01"),
                source("HCOFNULL002", "ACCTX002", "LAB", 720, "20261210", "H2002", "IL", branch="BX02"),
            ],
            [
                denial("HCOFNULL001", "ACCTX001", "E1", 710, "20261211", "D01", "H1", "IL", branch="BX01"),
                denial("HCOFNULL002", "ACCTX002", "LB", 720, "20261211", "D02", "H2002", "IL", branch="BX02"),
            ],
            ["20261210=OPEN"],
            [
                ofac("ACCTX001", "H1" + nul * 3, "CLEAR", "20261211"),
                ofac("ACCTX002", "H2002", "CLE" + nul * 2, "20261211"),
            ],
        )
        rows, summary = run_program()
        trace_rows = read_trace()

        assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED"]
        assert rows[0]["service"] == "ER"
        assert rows[1]["service"] == ""
        assert trace_rows == [
            {
                "action_record_id": "HCOFNULL001",
                "source_row": "0001",
                "source_date": "20261210",
            }
        ]
        assert summary["matched_amount_cents"] == 710
        assert summary["unmatched_amount_cents"] == 720

    def test_latest_applicable_ofac_decision_fails_closed(self):
        """The latest non-future OFAC decision must control and missing or malformed screens must block."""
        compile_program()
        write_inputs(
            [
                source("HCOFAC000001", "ACCT3001", "ER", 700, "20261215", "HF001", "NY", branch="BO01"),
                source("HCOFAC000002", "ACCT3002", "LAB", 800, "20261215", "HF002", "NY", branch="BO02"),
                source("HCOFAC000003", "ACCT3003", "IMG", 900, "20261215", "HF003", "NY", branch="BO03"),
                source("HCOFAC000004", "ACCT3004", "ER", 1000, "20261215", "HF004", "NY", branch="BO04"),
                source("HCOFAC000005", "ACCT3005", "ER", 1100, "20261215", "HF005", "NY", branch="BO05"),
            ],
            [
                denial("HCOFAC000001", "ACCT3001", "E1", 700, "20261220", "D01", "HF001", "NY", branch="BO01"),
                denial("HCOFAC000002", "ACCT3002", "LB", 800, "20261220", "D02", "HF002", "NY", branch="BO02"),
                denial("HCOFAC000003", "ACCT3003", "XR", 900, "20261220", "D17", "HF003", "NY", branch="BO03"),
                denial("HCOFAC000004", "ACCT3004", "E1", 1000, "20261220", "D01", "HF004", "NY", branch="BO04"),
                denial("HCOFAC000005", "ACCT3005", "E1", 1100, "20261220", "D01", "HF005", "NY", branch="BO05"),
            ],
            ["20261215=OPEN"],
            [
                ofac("ACCT3001", "HF001", "CLEAR", "20261216"),
                ofac("ACCT3001", "HF001", "HOLD", "20261219"),
                ofac("ACCT3002", "HF002", "HOLD", "20261216"),
                ofac("ACCT3002", "HF002", "clear", "20261219"),
                ofac("ACCT3003", "HF003", "CLEAR", "20261221"),
                ofac("ACCT3004", "HF004", "CLEAR", "BAD-DATE"),
                ofac("ACCT3005", "HF005", "CLEAR", "20261219"),
                ofac("ACCT3005", "HF005", "HOLD", "20261219"),
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == [
            "UNMATCHED",
            "MATCHED",
            "UNMATCHED",
            "UNMATCHED",
            "MATCHED",
        ]
        assert summary["matched_amount_cents"] == 1900
        assert summary["unmatched_amount_cents"] == 2600

    def test_ofac_rejection_does_not_consume_the_claim(self):
        """A blocked denial must leave its source row available for a later cleared denial."""
        compile_program()
        write_inputs(
            [source("HCRETRY00001", "ACCT4001", "ER", 1250, "20261222", "HR001", "WA", branch="BP01")],
            [
                denial("HCRETRY00001", "ACCT4001", "E1", 1250, "20261223", "D01", "HR001", "WA", branch="BP01"),
                denial("HCRETRY00001", "ACCT4001", "E1", 1250, "20261224", "D01", "HR001", "WA", branch="BP01"),
                denial("HCRETRY00001", "ACCT4001", "E1", 1250, "20261225", "D01", "HR001", "WA", branch="BP01"),
            ],
            ["20261222=OPEN"],
            [
                ofac("ACCT4001", "HR001", "HOLD", "20261223"),
                ofac("ACCT4001", "HR001", "CLEAR", "20261224"),
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["UNMATCHED", "MATCHED", "UNMATCHED"]
        assert [row["service"] for row in rows] == ["", "ER", ""]
        assert summary["matched_count"] == 1
        assert summary["unmatched_count"] == 2
