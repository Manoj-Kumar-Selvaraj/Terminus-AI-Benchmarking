from pathlib import Path
import shutil
import textwrap
import zipfile


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "New-Cobol-Tasks"
DEBIAN_DIGEST = "sha256:b29f74a267526ae6ea104eed6c46133b0ca70ce812525df8cd5817698f0a624a"


TASKS = [
    {
        "name": "cobol-hospital-claim-denial-reconciler",
        "domain": "hospital claim denial",
        "source_name": "claims",
        "action_name": "denials",
        "source_file": "claims.dat",
        "action_file": "denials.dat",
        "calendar_file": "adjudication_calendar.txt",
        "report": "denial_report.csv",
        "summary": "denial_summary.txt",
        "program": "claim_denial_reconcile",
        "category": "service",
        "source_status": "A",
        "allowed": ["ER", "LAB", "IMG"],
        "aliases": {"E1": "ER", "LB": "LAB", "XR": "IMG"},
        "reasons": ["D01", "D02", "D17"],
        "sample_prefix": "HC",
    },
    {
        "name": "cobol-rail-fare-adjustment-clearing",
        "domain": "rail fare adjustment",
        "source_name": "rides",
        "action_name": "adjustments",
        "source_file": "rides.dat",
        "action_file": "adjustments.dat",
        "calendar_file": "service_calendar.txt",
        "report": "adjustment_report.csv",
        "summary": "adjustment_summary.txt",
        "program": "fare_adjust_reconcile",
        "category": "fare_class",
        "source_status": "C",
        "allowed": ["STD", "EXP", "SNR"],
        "aliases": {"ST": "STD", "EX": "EXP", "SR": "SNR"},
        "reasons": ["F01", "F07", "F11"],
        "sample_prefix": "RF",
    },
    {
        "name": "cobol-warehouse-storage-credit-reconciler",
        "domain": "warehouse storage credit",
        "source_name": "charges",
        "action_name": "credits",
        "source_file": "charges.dat",
        "action_file": "credits.dat",
        "calendar_file": "billing_calendar.txt",
        "report": "credit_report.csv",
        "summary": "credit_summary.txt",
        "program": "storage_credit_reconcile",
        "category": "charge_type",
        "source_status": "B",
        "allowed": ["BIN", "FLT", "CLD"],
        "aliases": {"BN": "BIN", "FT": "FLT", "CD": "CLD"},
        "reasons": ["C04", "C08", "C19"],
        "sample_prefix": "WH",
    },
    {
        "name": "cobol-pension-contribution-reversal",
        "domain": "pension contribution reversal",
        "source_name": "contributions",
        "action_name": "reversals",
        "source_file": "contributions.dat",
        "action_file": "reversals.dat",
        "calendar_file": "posting_calendar.txt",
        "report": "reversal_report.csv",
        "summary": "reversal_summary.txt",
        "program": "pension_reversal_reconcile",
        "category": "bucket",
        "source_status": "P",
        "allowed": ["EMP", "ERD", "VOL"],
        "aliases": {"EE": "EMP", "ER": "ERD", "VL": "VOL"},
        "reasons": ["R02", "R05", "R14"],
        "sample_prefix": "PN",
    },
    {
        "name": "cobol-utility-meter-adjustment-clearing",
        "domain": "utility meter adjustment",
        "source_name": "readings",
        "action_name": "adjustments",
        "source_file": "readings.dat",
        "action_file": "meter_adjustments.dat",
        "calendar_file": "meter_calendar.txt",
        "report": "meter_adjustment_report.csv",
        "summary": "meter_adjustment_summary.txt",
        "program": "meter_adjust_reconcile",
        "category": "rate_code",
        "source_status": "R",
        "allowed": ["RES", "COM", "IND"],
        "aliases": {"RS": "RES", "CM": "COM", "IN": "IND"},
        "reasons": ["M03", "M09", "M12"],
        "sample_prefix": "UT",
    },
    {
        "name": "cobol-marina-docking-fee-reversal",
        "domain": "marina docking fee reversal",
        "source_name": "dock_fees",
        "action_name": "reversals",
        "source_file": "dock_fees.dat",
        "action_file": "reversals.dat",
        "calendar_file": "harbor_calendar.txt",
        "report": "docking_reversal_report.csv",
        "summary": "docking_reversal_summary.txt",
        "program": "docking_reversal_reconcile",
        "category": "berth_type",
        "source_status": "D",
        "allowed": ["SLP", "DRY", "TRN"],
        "aliases": {"SP": "SLP", "DY": "DRY", "TN": "TRN"},
        "reasons": ["H02", "H06", "H13"],
        "sample_prefix": "MR",
    },
    {
        "name": "cobol-courier-parcel-surcharge-credit",
        "domain": "courier parcel surcharge credit",
        "source_name": "shipments",
        "action_name": "credits",
        "source_file": "shipments.dat",
        "action_file": "credits.dat",
        "calendar_file": "dispatch_calendar.txt",
        "report": "surcharge_credit_report.csv",
        "summary": "surcharge_credit_summary.txt",
        "program": "parcel_credit_reconcile",
        "category": "service_tier",
        "source_status": "S",
        "allowed": ["STD", "NXT", "SAM"],
        "aliases": {"ST": "STD", "NX": "NXT", "SM": "SAM"},
        "reasons": ["P03", "P08", "P21"],
        "sample_prefix": "CP",
    },
    {
        "name": "cobol-museum-membership-dues-refund",
        "domain": "museum membership dues refund",
        "source_name": "dues",
        "action_name": "refunds",
        "source_file": "dues.dat",
        "action_file": "refunds.dat",
        "calendar_file": "membership_calendar.txt",
        "report": "dues_refund_report.csv",
        "summary": "dues_refund_summary.txt",
        "program": "membership_refund_reconcile",
        "category": "plan_code",
        "source_status": "M",
        "allowed": ["ANN", "FAM", "STU"],
        "aliases": {"AN": "ANN", "FM": "FAM", "SU": "STU"},
        "reasons": ["U01", "U07", "U15"],
        "sample_prefix": "MM",
    },
    {
        "name": "cobol-aviation-hangar-rent-adjustment",
        "domain": "aviation hangar rent adjustment",
        "source_name": "invoices",
        "action_name": "adjustments",
        "source_file": "invoices.dat",
        "action_file": "adjustments.dat",
        "calendar_file": "hangar_calendar.txt",
        "report": "hangar_adjustment_report.csv",
        "summary": "hangar_adjustment_summary.txt",
        "program": "hangar_adjust_reconcile",
        "category": "hangar_class",
        "source_status": "H",
        "allowed": ["PRM", "STD", "ECO"],
        "aliases": {"PM": "PRM", "ST": "STD", "EC": "ECO"},
        "reasons": ["A04", "A10", "A18"],
        "sample_prefix": "AV",
    },
    {
        "name": "cobol-telehealth-session-credit-clearing",
        "domain": "telehealth session credit",
        "source_name": "sessions",
        "action_name": "credits",
        "source_file": "sessions.dat",
        "action_file": "credits.dat",
        "calendar_file": "provider_calendar.txt",
        "report": "session_credit_report.csv",
        "summary": "session_credit_summary.txt",
        "program": "session_credit_reconcile",
        "category": "visit_type",
        "source_status": "T",
        "allowed": ["GEN", "SPC", "URG"],
        "aliases": {"GN": "GEN", "SC": "SPC", "UG": "URG"},
        "reasons": ["V02", "V09", "V16"],
        "sample_prefix": "TH",
    },
]


def lower_first(text: str) -> str:
    return text[:1].lower() + text[1:]


def record_source(rid, acct, cat, amt, date, status, branch):
    return f"S{rid:<12}{acct:<8}{cat:<3}{amt:010d}{date}{status}{branch:<4}"


def record_action(rid, acct, cat, amt, date, reason, branch):
    return f"A{rid:<12}{acct:<8}{cat:<3}{amt:010d}{date}{reason:<3}{branch:<4}"


def common_cobol(task, variant: str) -> str:
    """variant: seed (broken), m1, m2, or m3 oracle implementations."""
    eligible_reason = "\n               OR ".join(f'ACT-REASON = "{reason}"' for reason in task["reasons"])
    allowed_source = "\n               OR ".join(f'SRC-CAT(I) = "{code}"' for code in task["allowed"])
    alias_checks = []
    for alias, canon in task["aliases"].items():
        width = len(alias)
        alias_checks.append(
            f'           IF ACT-CAT(1:{width}) = "{alias}"\n'
            f'               MOVE "{canon}" TO CANON-CAT\n'
            f"           END-IF"
        )
    alias_lines = "\n".join(alias_checks)
    base_match = textwrap.dedent(
        f"""
                         AND SRC-BRANCH(I) = ACT-BRANCH
                         AND SRC-USED(I) NOT = "Y"
                         AND SRC-STATUS(I) = "{task['source_status']}"
                         AND ( {allowed_source} )
                         AND ( {eligible_reason} )
                         AND FUNCTION NUMVAL(ACT-DATE) >= FUNCTION NUMVAL(SRC-DATE(I))
        """
    ).rstrip()

    if variant == "seed":
        match_extra = ""
        category_prepare = "           MOVE ACT-CAT TO CANON-CAT\n"
        match_loop_stop = " OR MATCHED-FLAG = \"Y\""
        match_body = """                   MOVE "Y" TO MATCHED-FLAG
                   MOVE I TO MATCH-IDX
                   CONTINUE"""
        finalize_match = ""
    elif variant == "m1":
        match_extra = base_match
        category_prepare = "           MOVE ACT-CAT TO CANON-CAT\n"
        match_loop_stop = " OR MATCHED-FLAG = \"Y\""
        match_body = """                   MOVE "Y" TO MATCHED-FLAG
                   MOVE I TO MATCH-IDX
                   MOVE "Y" TO SRC-USED(I)"""
        finalize_match = ""
    elif variant == "m2":
        match_extra = base_match
        category_prepare = f"""
           MOVE ACT-CAT TO CANON-CAT
{alias_lines}
"""
        match_loop_stop = " OR MATCHED-FLAG = \"Y\""
        match_body = """                   MOVE "Y" TO MATCHED-FLAG
                   MOVE I TO MATCH-IDX
                   MOVE "Y" TO SRC-USED(I)"""
        finalize_match = ""
    elif variant == "m3":
        match_extra = base_match + '\n                         AND OPEN-FLAG = "Y"'
        category_prepare = f"""
           MOVE ACT-CAT TO CANON-CAT
{alias_lines}
"""
        match_loop_stop = ""
        match_body = """                   IF MATCHED-FLAG = "N"
                       MOVE "Y" TO MATCHED-FLAG
                       MOVE I TO MATCH-IDX
                   ELSE
                       IF FUNCTION NUMVAL(SRC-DATE(I)) > FUNCTION NUMVAL(SRC-DATE(MATCH-IDX))
                           OR (SRC-DATE(I) = SRC-DATE(MATCH-IDX) AND I < MATCH-IDX)
                           MOVE I TO MATCH-IDX
                       END-IF
                   END-IF"""
        finalize_match = """           IF MATCHED-FLAG = "Y"
               MOVE "Y" TO SRC-USED(MATCH-IDX)
           END-IF
"""
    else:
        raise ValueError(f"unknown variant {variant}")

    return f"""       IDENTIFICATION DIVISION.
       PROGRAM-ID. {task['program'].replace('_', '-')}.
       ENVIRONMENT DIVISION.
       INPUT-OUTPUT SECTION.
       FILE-CONTROL.
           SELECT SRC-FILE ASSIGN TO "/app/data/{task['source_file']}"
               ORGANIZATION IS LINE SEQUENTIAL.
           SELECT ACT-FILE ASSIGN TO "/app/data/{task['action_file']}"
               ORGANIZATION IS LINE SEQUENTIAL.
           SELECT CAL-FILE ASSIGN TO "/app/config/{task['calendar_file']}"
               ORGANIZATION IS LINE SEQUENTIAL.
           SELECT REP-FILE ASSIGN TO "/app/out/{task['report']}"
               ORGANIZATION IS LINE SEQUENTIAL.
           SELECT SUM-FILE ASSIGN TO "/app/out/{task['summary']}"
               ORGANIZATION IS LINE SEQUENTIAL.
       DATA DIVISION.
       FILE SECTION.
       FD SRC-FILE.
       01 SRC-LINE PIC X(80).
       FD ACT-FILE.
       01 ACT-LINE PIC X(80).
       FD CAL-FILE.
       01 CAL-LINE PIC X(80).
       FD REP-FILE.
       01 REP-LINE PIC X(200).
       FD SUM-FILE.
       01 SUM-LINE PIC X(80).
       WORKING-STORAGE SECTION.
       01 EOF-SRC PIC X VALUE "N".
       01 EOF-ACT PIC X VALUE "N".
       01 EOF-CAL PIC X VALUE "N".
       01 SRC-COUNT PIC 9(4) VALUE 0.
       01 CAL-COUNT PIC 9(4) VALUE 0.
       01 I PIC 9(4) VALUE 0.
       01 CAL-IDX PIC 9(4) VALUE 0.
       01 MATCH-IDX PIC 9(4) VALUE 0.
       01 OPEN-FLAG PIC X VALUE "N".
       01 MATCHED-FLAG PIC X VALUE "N".
       01 CHECK-DATE PIC X(8).
       01 CANON-CAT PIC X(3).
       01 WORK-AMOUNT PIC 9(10) VALUE 0.
       01 MATCHED-COUNT PIC 9(8) VALUE 0.
       01 UNMATCHED-COUNT PIC 9(8) VALUE 0.
       01 MATCHED-AMOUNT PIC 9(12) VALUE 0.
       01 UNMATCHED-AMOUNT PIC 9(12) VALUE 0.
       01 ACT-ID PIC X(12).
       01 ACT-ACCT PIC X(8).
       01 ACT-CAT PIC X(3).
       01 ACT-AMT PIC X(10).
       01 ACT-DATE PIC X(8).
       01 ACT-REASON PIC X(3).
       01 ACT-BRANCH PIC X(4).
       01 SRC-TABLE.
          05 SRC-ROW OCCURS 200 TIMES.
             10 SRC-ID PIC X(12).
             10 SRC-ACCT PIC X(8).
             10 SRC-CAT PIC X(3).
             10 SRC-AMT PIC X(10).
             10 SRC-DATE PIC X(8).
             10 SRC-STATUS PIC X.
             10 SRC-BRANCH PIC X(4).
             10 SRC-USED PIC X.
       01 CAL-TABLE.
          05 CAL-ROW OCCURS 100 TIMES.
             10 CAL-DATE PIC X(8).
             10 CAL-STATE PIC X(4).
       PROCEDURE DIVISION.
       MAIN-PARA.
           CALL "SYSTEM" USING "mkdir -p /app/out"
           PERFORM LOAD-SOURCES
           PERFORM LOAD-CALENDAR
           OPEN INPUT ACT-FILE
           OPEN OUTPUT REP-FILE SUM-FILE
           MOVE SPACES TO REP-LINE
           MOVE "record_id,account,{task['category']},amount_cents,reason,status" TO REP-LINE
           WRITE REP-LINE
           PERFORM UNTIL EOF-ACT = "Y"
               READ ACT-FILE
                   AT END MOVE "Y" TO EOF-ACT
                   NOT AT END PERFORM PROCESS-ACTION
               END-READ
           END-PERFORM
           PERFORM WRITE-SUMMARY
           CLOSE ACT-FILE REP-FILE SUM-FILE
           STOP RUN.

       LOAD-SOURCES.
           OPEN INPUT SRC-FILE
           PERFORM UNTIL EOF-SRC = "Y"
               READ SRC-FILE
                   AT END MOVE "Y" TO EOF-SRC
                   NOT AT END
                       ADD 1 TO SRC-COUNT
                       MOVE SRC-LINE(2:12) TO SRC-ID(SRC-COUNT)
                       MOVE SRC-LINE(14:8) TO SRC-ACCT(SRC-COUNT)
                       MOVE SRC-LINE(22:3) TO SRC-CAT(SRC-COUNT)
                       MOVE SRC-LINE(25:10) TO SRC-AMT(SRC-COUNT)
                       MOVE SRC-LINE(35:8) TO SRC-DATE(SRC-COUNT)
                       MOVE SRC-LINE(43:1) TO SRC-STATUS(SRC-COUNT)
                       MOVE SRC-LINE(44:4) TO SRC-BRANCH(SRC-COUNT)
                       MOVE "N" TO SRC-USED(SRC-COUNT)
               END-READ
           END-PERFORM
           CLOSE SRC-FILE.

       LOAD-CALENDAR.
           OPEN INPUT CAL-FILE
           PERFORM UNTIL EOF-CAL = "Y"
               READ CAL-FILE
                   AT END MOVE "Y" TO EOF-CAL
                   NOT AT END
                       ADD 1 TO CAL-COUNT
                       MOVE CAL-LINE(1:8) TO CAL-DATE(CAL-COUNT)
                       MOVE CAL-LINE(10:4) TO CAL-STATE(CAL-COUNT)
               END-READ
           END-PERFORM
           CLOSE CAL-FILE.

       PROCESS-ACTION.
           MOVE ACT-LINE(2:12) TO ACT-ID
           MOVE ACT-LINE(14:8) TO ACT-ACCT
           MOVE ACT-LINE(22:3) TO ACT-CAT
           MOVE ACT-LINE(25:10) TO ACT-AMT
           MOVE ACT-LINE(35:8) TO ACT-DATE
           MOVE ACT-LINE(43:3) TO ACT-REASON
           MOVE ACT-LINE(46:4) TO ACT-BRANCH
{category_prepare.rstrip()}
           MOVE "N" TO MATCHED-FLAG
           MOVE 0 TO MATCH-IDX
           PERFORM VARYING I FROM 1 BY 1 UNTIL I > SRC-COUNT{match_loop_stop}
               MOVE SRC-DATE(I) TO CHECK-DATE
               PERFORM CHECK-CALENDAR
               IF ACT-ID = SRC-ID(I)
                  AND ACT-ACCT = SRC-ACCT(I)
                  AND CANON-CAT = SRC-CAT(I)
                  AND ACT-AMT = SRC-AMT(I)
{textwrap.indent(match_extra, '                 ')}
{match_body}
               END-IF
           END-PERFORM
{finalize_match}           MOVE ACT-AMT TO WORK-AMOUNT
           IF MATCHED-FLAG = "Y"
               ADD 1 TO MATCHED-COUNT
               ADD WORK-AMOUNT TO MATCHED-AMOUNT
               MOVE SPACES TO REP-LINE
               STRING ACT-ID DELIMITED BY SPACE "," ACT-ACCT DELIMITED BY SPACE ","
                      SRC-CAT(MATCH-IDX) DELIMITED BY SPACE "," ACT-AMT DELIMITED BY SIZE ","
                      ACT-REASON DELIMITED BY SPACE ",MATCHED"
                      DELIMITED BY SIZE INTO REP-LINE
               END-STRING
           ELSE
               ADD 1 TO UNMATCHED-COUNT
               ADD WORK-AMOUNT TO UNMATCHED-AMOUNT
               MOVE SPACES TO REP-LINE
               STRING ACT-ID DELIMITED BY SPACE "," ACT-ACCT DELIMITED BY SPACE ",,"
                      ACT-AMT DELIMITED BY SIZE "," ACT-REASON DELIMITED BY SPACE ",UNMATCHED"
                      DELIMITED BY SIZE INTO REP-LINE
               END-STRING
           END-IF
           WRITE REP-LINE.

       CHECK-CALENDAR.
           MOVE "N" TO OPEN-FLAG
           IF CHECK-DATE IS NUMERIC AND ACT-DATE IS NUMERIC
               PERFORM VARYING CAL-IDX FROM 1 BY 1 UNTIL CAL-IDX > CAL-COUNT OR OPEN-FLAG = "Y"
                   IF CAL-DATE(CAL-IDX) = CHECK-DATE
                      AND (CAL-STATE(CAL-IDX) = "OPEN"
                        OR CAL-STATE(CAL-IDX) = "open")
                       MOVE "Y" TO OPEN-FLAG
                   END-IF
               END-PERFORM
           END-IF.

       WRITE-SUMMARY.
           MOVE SPACES TO SUM-LINE
           STRING "matched_count=" MATCHED-COUNT DELIMITED BY SIZE INTO SUM-LINE END-STRING
           WRITE SUM-LINE
           MOVE SPACES TO SUM-LINE
           STRING "matched_amount_cents=" MATCHED-AMOUNT DELIMITED BY SIZE INTO SUM-LINE END-STRING
           WRITE SUM-LINE
           MOVE SPACES TO SUM-LINE
           STRING "unmatched_count=" UNMATCHED-COUNT DELIMITED BY SIZE INTO SUM-LINE END-STRING
           WRITE SUM-LINE
           MOVE SPACES TO SUM-LINE
           STRING "unmatched_amount_cents=" UNMATCHED-AMOUNT DELIMITED BY SIZE INTO SUM-LINE END-STRING
           WRITE SUM-LINE.
"""


def test_common_header(task) -> str:
    return f'''"""Verifier tests for the {task["domain"]} COBOL reconciler."""

import csv
import subprocess
from pathlib import Path


APP = Path("/app")
SRC = APP / "src" / "{task['program']}.cbl"
BIN = APP / "build" / "{task['program']}"
SOURCE = APP / "data" / "{task['source_file']}"
ACTION = APP / "data" / "{task['action_file']}"
CALENDAR = APP / "config" / "{task['calendar_file']}"
REPORT = APP / "out" / "{task['report']}"
SUMMARY = APP / "out" / "{task['summary']}"


def src(record_id, account, category, amount, date, status="{task['source_status']}", branch="B001"):
    """Create one fixed-width source record."""
    return f"S{{record_id:<12}}{{account:<8}}{{category:<3}}{{amount:010d}}{{date}}{{status}}{{branch:<4}}"


def action(record_id, account, category, amount, date, reason, branch="B001"):
    """Create one fixed-width action record."""
    return f"A{{record_id:<12}}{{account:<8}}{{category:<3}}{{amount:010d}}{{date}}{{reason:<3}}{{branch:<4}}"


def compile_program():
    """Compile the COBOL program for a verifier scenario."""
    BIN.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["cobc", "-x", "-free", "-O2", "-o", str(BIN), str(SRC)], check=True, cwd=APP)


def write_inputs(source_lines, action_lines, calendar_lines):
    """Replace input files so outputs cannot be precomputed from shipped fixtures."""
    SOURCE.write_text("\\n".join(source_lines) + "\\n")
    ACTION.write_text("\\n".join(action_lines) + "\\n")
    CALENDAR.write_text("\\n".join(calendar_lines) + "\\n")
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.unlink(missing_ok=True)
    SUMMARY.unlink(missing_ok=True)


def run_program():
    """Run the reconciler and return parsed report and summary data."""
    subprocess.run([str(BIN)], check=True, cwd=APP)
    with REPORT.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    summary = {{}}
    for raw in SUMMARY.read_text().splitlines():
        key, value = raw.split("=", 1)
        summary[key] = int(value)
    return rows, summary
'''


def test_m1_py(task) -> str:
    allowed_a, allowed_b, allowed_c = task["allowed"]
    alias_a, alias_b, alias_c = list(task["aliases"].keys())
    canon_alias_a, canon_alias_b, canon_alias_c = list(task["aliases"].values())
    reason_a, reason_b, reason_c = task["reasons"]
    p = task["sample_prefix"]
    return test_common_header(task) + f'''

def test_core_keys_status_reason_and_category_match_with_positive_totals():
    """Canonical categories should match through full keys, status, reason, and branch gates."""
    compile_program()
    write_inputs(
        [
            src("{p}0000000001", "ACCT1001", "{canon_alias_a}", 1200, "20260501", branch="BR01"),
            src("{p}0000000002", "ACCT1002", "{canon_alias_b}", 3400, "20260502", branch="BR02"),
            src("{p}0000000003", "ACCT1003", "{canon_alias_c}", 5600, "20260503", branch="BR03"),
        ],
        [
            action("{p}0000000001", "ACCT1001", "{canon_alias_a}", 1200, "20260504", "{reason_a}", branch="BR01"),
            action("{p}0000000002", "ACCT1002", "{canon_alias_b}", 3400, "20260505", "{reason_b}", branch="BR02"),
            action("{p}0000000003", "ACCT1003", "{canon_alias_c}", 5600, "20260506", "{reason_c}", branch="BR03"),
        ],
        ["20260501=OPEN", "20260502=OPEN", "20260503=OPEN"],
    )
    rows, summary = run_program()

    assert REPORT.read_text().splitlines()[0] == "record_id,account,{task['category']},amount_cents,reason,status"
    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "MATCHED"]
    assert [row["{task['category']}"] for row in rows] == ["{canon_alias_a}", "{canon_alias_b}", "{canon_alias_c}"]
    assert summary == {{
        "matched_count": 3,
        "matched_amount_cents": 10200,
        "unmatched_count": 0,
        "unmatched_amount_cents": 0,
    }}


def test_every_matching_gate_can_reject_a_candidate_without_reusing_rows():
    """Status, amount, account, branch, reason, date, category, and row consumption all gate matching."""
    compile_program()
    write_inputs(
        [
            src("{p}GATE000001", "ACCT2001", "{allowed_a}", 1000, "20260510", branch="BA01"),
            src("{p}GATE000002", "ACCT2002", "{allowed_a}", 2000, "20260510", status="X", branch="BA02"),
            src("{p}GATE000003", "ACCT2003", "{allowed_b}", 3000, "20260511", branch="BA03"),
            src("{p}GATE000004", "ACCT2004", "BAD", 4000, "20260512", branch="BA04"),
            src("{p}GATE000005", "ACCT2005", "{allowed_c}", 5000, "20260513", branch="BA05"),
        ],
        [
            action("{p}GATE000001", "ACCT2001", "{allowed_a}", 1000, "20260514", "{reason_a}", branch="BA01"),
            action("{p}GATE000001", "ACCT2001", "{allowed_a}", 1000, "20260514", "{reason_a}", branch="BA01"),
            action("{p}GATE000002", "ACCT2002", "{allowed_a}", 2000, "20260514", "{reason_a}", branch="BA02"),
            action("{p}GATE000003", "ACCT2999", "{allowed_b}", 3000, "20260514", "{reason_b}", branch="BA03"),
            action("{p}GATE000003", "ACCT2003", "{allowed_b}", 3999, "20260514", "{reason_b}", branch="BA03"),
            action("{p}GATE000003", "ACCT2003", "{allowed_b}", 3000, "20260509", "{reason_b}", branch="BA03"),
            action("{p}GATE000003", "ACCT2003", "{allowed_b}", 3000, "20260514", "BAD", branch="BA03"),
            action("{p}GATE000004", "ACCT2004", "BAD", 4000, "20260514", "{reason_a}", branch="BA04"),
            action("{p}GATE000005", "ACCT2005", "{allowed_c}", 5000, "20260514", "{reason_c}", branch="ZZ99"),
        ],
        ["20260510=OPEN", "20260511=OPEN", "20260512=OPEN", "20260513=OPEN"],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == [
        "MATCHED",
        "UNMATCHED",
        "UNMATCHED",
        "UNMATCHED",
        "UNMATCHED",
        "UNMATCHED",
        "UNMATCHED",
        "UNMATCHED",
        "UNMATCHED",
    ]
    assert rows[1]["{task['category']}"] == ""
    assert rows[8]["account"] == "ACCT2005"
    assert summary["matched_count"] == 1
    assert summary["matched_amount_cents"] == 1000
    assert summary["unmatched_count"] == 8
    assert summary["unmatched_amount_cents"] == 24999


def test_report_keeps_action_order_blank_unmatched_category_and_positive_totals():
    """Output should keep action order, blank unmatched categories, exact statuses, and positive cent totals."""
    compile_program()
    write_inputs(
        [
            src("{p}ORDER0001", "ACCT4001", "{allowed_a}", 101, "20260601", branch="BD01"),
            src("{p}ORDER0002", "ACCT4002", "{allowed_b}", 202, "20260601", branch="BD02"),
            src("{p}ORDER0003", "ACCT4003", "{allowed_c}", 303, "20260601", branch="BD03"),
        ],
        [
            action("{p}ORDER0003", "ACCT4003", "{allowed_c}", 303, "20260602", "{reason_c}", branch="BD03"),
            action("{p}ORDER0002", "ACCT4002", "{allowed_b}", 999, "20260602", "{reason_b}", branch="BD02"),
            action("{p}ORDER0001", "ACCT4001", "{allowed_a}", 101, "20260602", "{reason_a}", branch="BD01"),
        ],
        ["20260601=OPEN"],
    )
    rows, summary = run_program()

    assert [row["record_id"] for row in rows] == ["{p}ORDER0003", "{p}ORDER0002", "{p}ORDER0001"]
    assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED", "MATCHED"]
    assert rows[1]["{task['category']}"] == ""
    assert [row["amount_cents"] for row in rows] == ["0000000303", "0000000999", "0000000101"]
    assert summary["matched_count"] == 2
    assert summary["matched_amount_cents"] == 404
    assert summary["unmatched_count"] == 1
    assert summary["unmatched_amount_cents"] == 999
'''


def test_m2_py(task) -> str:
    allowed_a, allowed_b, allowed_c = task["allowed"]
    alias_a, alias_b, alias_c = list(task["aliases"].keys())
    canon_alias_a, canon_alias_b, canon_alias_c = list(task["aliases"].values())
    reason_a, reason_b, reason_c = task["reasons"]
    p = task["sample_prefix"]
    return test_common_header(task) + f'''

def test_legacy_aliases_match_and_emit_canonical_categories():
    """Legacy aliases should normalize to canonical categories before matching and in the report."""
    compile_program()
    write_inputs(
        [
            src("{p}AL00000001", "ACCT5001", "{canon_alias_a}", 1500, "20260701", branch="BE01"),
            src("{p}AL00000002", "ACCT5002", "{canon_alias_b}", 2500, "20260701", branch="BE02"),
            src("{p}AL00000003", "ACCT5003", "{canon_alias_c}", 3500, "20260701", branch="BE03"),
        ],
        [
            action("{p}AL00000001", "ACCT5001", "{alias_a}", 1500, "20260702", "{reason_a}", branch="BE01"),
            action("{p}AL00000002", "ACCT5002", "{alias_b}", 2500, "20260702", "{reason_b}", branch="BE02"),
            action("{p}AL00000003", "ACCT5003", "{alias_c}", 3500, "20260702", "{reason_c}", branch="BE03"),
        ],
        ["20260701=OPEN"],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "MATCHED"]
    assert [row["{task['category']}"] for row in rows] == ["{canon_alias_a}", "{canon_alias_b}", "{canon_alias_c}"]
    assert summary["matched_count"] == 3


def test_duplicate_actions_do_not_reuse_the_same_source_row():
    """Only the first eligible action may consume a matching source row."""
    compile_program()
    write_inputs(
        [src("{p}DUP0000001", "ACCT6001", "{allowed_a}", 900, "20260710", branch="BF01")],
        [
            action("{p}DUP0000001", "ACCT6001", "{allowed_a}", 900, "20260711", "{reason_a}", branch="BF01"),
            action("{p}DUP0000001", "ACCT6001", "{allowed_a}", 900, "20260712", "{reason_a}", branch="BF01"),
        ],
        ["20260710=OPEN"],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED"]
    assert rows[1]["{task['category']}"] == ""
    assert summary == {{
        "matched_count": 1,
        "matched_amount_cents": 900,
        "unmatched_count": 1,
        "unmatched_amount_cents": 900,
    }}
'''


def test_m3_py(task) -> str:
    allowed_a, allowed_b, allowed_c = task["allowed"]
    alias_a, alias_b, alias_c = list(task["aliases"].keys())
    canon_alias_a, canon_alias_b, canon_alias_c = list(task["aliases"].values())
    reason_a, reason_b, reason_c = task["reasons"]
    p = task["sample_prefix"]
    return test_common_header(task) + f'''

def test_closed_missing_and_malformed_calendar_dates_stay_unmatched():
    """Closed, missing, malformed, or unlisted source dates should never be treated as open."""
    compile_program()
    write_inputs(
        [
            src("{p}CAL0000001", "ACCT3001", "{allowed_a}", 1111, "20260520", branch="BC01"),
            src("{p}CAL0000002", "ACCT3002", "{allowed_b}", 2222, "20260521", branch="BC02"),
            src("{p}CAL0000003", "ACCT3003", "{allowed_c}", 3333, "20260522", branch="BC03"),
            src("{p}CAL0000004", "ACCT3004", "{allowed_a}", 4444, "BAD-DATE", branch="BC04"),
        ],
        [
            action("{p}CAL0000001", "ACCT3001", "{allowed_a}", 1111, "20260523", "{reason_a}", branch="BC01"),
            action("{p}CAL0000002", "ACCT3002", "{allowed_b}", 2222, "20260523", "{reason_b}", branch="BC02"),
            action("{p}CAL0000003", "ACCT3003", "{allowed_c}", 3333, "20260523", "{reason_c}", branch="BC03"),
            action("{p}CAL0000004", "ACCT3004", "{allowed_a}", 4444, "20260523", "{reason_a}", branch="BC04"),
        ],
        ["20260520=OPEN", "20260521=CLOS", "BAD-DATE=OPEN"],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED"]
    assert summary["matched_amount_cents"] == 1111
    assert summary["unmatched_amount_cents"] == 9999


def test_latest_source_date_wins_when_multiple_rows_qualify():
    """Among eligible source rows, the latest open source date should win for a single action."""
    compile_program()
    write_inputs(
        [
            src("{p}LAT0000001", "ACCT7001", "{allowed_a}", 1000, "20260801", branch="BG01"),
            src("{p}LAT0000001", "ACCT7001", "{allowed_a}", 1000, "20260805", branch="BG01"),
            src("{p}LAT0000001", "ACCT7001", "{allowed_a}", 1000, "20260803", branch="BG01"),
        ],
        [action("{p}LAT0000001", "ACCT7001", "{alias_a}", 1000, "20260810", "{reason_a}", branch="BG01")],
        ["20260801=OPEN", "20260803=OPEN", "20260805=OPEN", "20260810=OPEN"],
    )
    rows, summary = run_program()

    assert rows[0]["status"] == "MATCHED"
    assert rows[0]["{task['category']}"] == "{canon_alias_a}"
    assert summary == {{
        "matched_count": 1,
        "matched_amount_cents": 1000,
        "unmatched_count": 0,
        "unmatched_amount_cents": 0,
    }}


def test_second_action_stays_unmatched_after_latest_source_row_is_consumed():
    """Once the only eligible source row is consumed, a second duplicate action must remain unmatched."""
    compile_program()
    write_inputs(
        [src("{p}LAT0000002", "ACCT7002", "{allowed_a}", 1000, "20260805", branch="BG01")],
        [
            action("{p}LAT0000002", "ACCT7002", "{alias_a}", 1000, "20260810", "{reason_a}", branch="BG01"),
            action("{p}LAT0000002", "ACCT7002", "{alias_a}", 1000, "20260811", "{reason_a}", branch="BG01"),
        ],
        ["20260805=OPEN", "20260810=OPEN", "20260811=OPEN"],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED"]
    assert summary["matched_count"] == 1
    assert summary["unmatched_amount_cents"] == 1000


def test_aliases_still_work_under_calendar_gates():
    """Alias normalization must still apply when calendar gates are enforced."""
    compile_program()
    write_inputs(
        [src("{p}ALM3000001", "ACCT8001", "{canon_alias_c}", 650, "20260901", branch="BH01")],
        [action("{p}ALM3000001", "ACCT8001", "{alias_c}", 650, "20260902", "{reason_c}", branch="BH01")],
        ["20260901=OPEN", "20260902=OPEN"],
    )
    rows, summary = run_program()

    assert rows[0]["status"] == "MATCHED"
    assert rows[0]["{task['category']}"] == "{canon_alias_c}"
    assert summary["matched_amount_cents"] == 650
'''


def instruction_m1(task) -> str:
    allowed = ", ".join(f"`{x}`" for x in task["allowed"])
    reasons = ", ".join(f"`{x}`" for x in task["reasons"])
    return f"""The COBOL {task['domain']} reconciler in `/app/src/{task['program']}.cbl` is producing unreliable clearing reports. Fix it so it reconciles `/app/data/{task['source_file']}` with `/app/data/{task['action_file']}` and writes the required outputs under `/app/out`.

The source records and action records are fixed-width files documented in `/app/docs/record_layouts.md`. A row matches only when the full 12-character record id, 8-character account, 10-digit amount, 4-character branch, source status `{task['source_status']}`, eligible action reason, and allowed canonical {task['category']} all agree. Allowed canonical {task['category']} values are {allowed}. Eligible action reasons are {reasons}. The action date must be on or after the matched source date. Each source row can be consumed once.

Write `/app/out/{task['report']}` with columns `record_id,account,{task['category']},amount_cents,reason,status`, preserving action input order and the zero-padded amount text. Write `/app/out/{task['summary']}` as `key=value` lines for `matched_count`, `matched_amount_cents`, `unmatched_count`, and `unmatched_amount_cents`, with all amounts counted as positive integer cents.
"""


def instruction_m2(task) -> str:
    aliases = ", ".join(f"`{a}` means `{c}`" for a, c in task["aliases"].items())
    return f"""Continue the {task['domain']} reconciler in `/app/src/{task['program']}.cbl`. Keep milestone 1 matching, report schema, and summary semantics.

Legacy action {task['category']} aliases must be normalized before matching and report output: {aliases}. Matched rows report the canonical source {task['category']}; unmatched rows leave that column blank. Each source row can still be consumed at most once, with the earliest eligible action winning when duplicate action rows target the same source row.
"""


def instruction_m3(task) -> str:
    return f"""Finish the {task['domain']} reconciler in `/app/src/{task['program']}.cbl` by applying calendar gates from `/app/config/{task['calendar_file']}` while preserving milestone 1-2 behavior.

Source dates are eligible only when the same date appears in the calendar file with the literal state `OPEN` compared case-insensitively; closed, missing, unlisted, or malformed dates are ineligible. All earlier matching gates still apply, including aliases, consumption, status `{task['source_status']}`, reasons, and allowed categories.

When more than one unused source row matches an action, choose the eligible row with the latest source date. If source dates tie, choose the earliest source input row. Consumption is tracked by source row position, not by record id alone.
"""


def instruction(task) -> str:
    aliases = ", ".join(f"`{a}` means `{c}`" for a, c in task["aliases"].items())
    allowed = ", ".join(f"`{x}`" for x in task["allowed"])
    reasons = ", ".join(f"`{x}`" for x in task["reasons"])
    return f"""The COBOL {task['domain']} reconciler in `/app/src/{task['program']}.cbl` is producing unreliable clearing reports. Fix it so it reconciles `/app/data/{task['source_file']}` with `/app/data/{task['action_file']}` and writes the required outputs under `/app/out`.

The source records and action records are fixed-width files. A row matches only when the full 12-character record id, 8-character account, 10-digit amount, 4-character branch, source status `{task['source_status']}`, eligible action reason, allowed canonical {task['category']}, and date rules all agree. Allowed canonical {task['category']} values are {allowed}. Eligible action reasons are {reasons}. Source dates are eligible only when the same date appears in `/app/config/{task['calendar_file']}` with the literal state `OPEN`; closed, missing, unlisted, or malformed dates are ineligible. The action date must be on or after the matched source date.

Legacy action {task['category']} aliases must be normalized before matching and report output: {aliases}. Matched rows report the canonical source {task['category']}; unmatched rows leave that column blank. Each source row can be consumed once, even when duplicate action rows appear.

Write `/app/out/{task['report']}` with columns `record_id,account,{task['category']},amount_cents,reason,status`, preserving action input order and the zero-padded amount text. Write `/app/out/{task['summary']}` as `key=value` lines for `matched_count`, `matched_amount_cents`, `unmatched_count`, and `unmatched_amount_cents`, with all amounts counted as positive integer cents.
"""


def solve_sh(task, milestone: int) -> str:
    lines = ["#!/bin/bash", "set -euo pipefail", 'SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"']
    for number in range(1, milestone + 1):
        lines.append(f'bash "$SCRIPT_DIR/solve{number}.sh"')
    return "\n".join(lines) + "\n"


def solve1_sh(task) -> str:
    body = common_cobol(task, "m1")
    return f"""#!/bin/bash
set -euo pipefail
if grep -q 'SRC-USED(I) NOT = "Y"' /app/src/{task['program']}.cbl; then
  /app/scripts/run_batch.sh
  exit 0
fi
cat > /app/src/{task['program']}.cbl <<'COBOL'
{body}COBOL
/app/scripts/run_batch.sh
"""


def solve2_sh(task) -> str:
    body = common_cobol(task, "m2")
    alias = next(iter(task["aliases"]))
    return f"""#!/bin/bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${{BASH_SOURCE[0]}}")" && pwd)"
if ! grep -q 'SRC-USED(I) NOT = "Y"' /app/src/{task['program']}.cbl; then
  bash "$SCRIPT_DIR/solve1.sh"
fi
if grep -q 'IF ACT-CAT(1:{len(alias)}) = "{alias}"' /app/src/{task['program']}.cbl; then
  /app/scripts/run_batch.sh
  exit 0
fi
cat > /app/src/{task['program']}.cbl <<'COBOL'
{body}COBOL
/app/scripts/run_batch.sh
"""


def solve3_sh(task) -> str:
    body = common_cobol(task, "m3")
    alias = next(iter(task["aliases"]))
    return f"""#!/bin/bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${{BASH_SOURCE[0]}}")" && pwd)"
if ! grep -q 'SRC-USED(I) NOT = "Y"' /app/src/{task['program']}.cbl; then
  bash "$SCRIPT_DIR/solve1.sh"
fi
if ! grep -q 'IF ACT-CAT(1:{len(alias)}) = "{alias}"' /app/src/{task['program']}.cbl; then
  bash "$SCRIPT_DIR/solve2.sh"
fi
if grep -q 'FUNCTION NUMVAL(SRC-DATE(I)) > FUNCTION NUMVAL(SRC-DATE(MATCH-IDX))' /app/src/{task['program']}.cbl; then
  /app/scripts/run_batch.sh
  exit 0
fi
cat > /app/src/{task['program']}.cbl <<'COBOL'
{body}COBOL
/app/scripts/run_batch.sh
"""


def test_sh(milestone: int) -> str:
    return f"""#!/bin/bash
set -uo pipefail
mkdir -p /logs/verifier
echo 0 > /logs/verifier/reward.txt

pytest_status=1
trap 'exit $pytest_status' EXIT
if [ "$PWD" = "/" ]; then
    echo "Error: No working directory set. Please set a WORKDIR in your Dockerfile before running this script."
    exit 1
fi
python3 -m pytest --ctrf /logs/verifier/ctrf.json /tests/test_m{milestone}.py -rA
pytest_status=$?

test $pytest_status -eq 0
if [ $? -eq 0 ]; then
    echo 1 > /logs/verifier/reward.txt
else
    echo 0 > /logs/verifier/reward.txt
fi
"""


def dockerfile() -> str:
    return f"""FROM debian:bookworm-slim@{DEBIAN_DIGEST}

WORKDIR /app

RUN apt-get update \\
    && apt-get install -y --no-install-recommends bash ca-certificates gnucobol make python3 python3-pip \\
    && rm -rf /var/lib/apt/lists/*

RUN pip3 install --break-system-packages pytest==8.4.1 pytest-json-ctrf==0.3.5

COPY src/ /app/src/
COPY data/ /app/data/
COPY config/ /app/config/
COPY docs/ /app/docs/
COPY samples/ /app/samples/
COPY scripts/ /app/scripts/

RUN mkdir -p /app/out /app/build \\
    && chmod +x /app/scripts/*.sh
"""


def task_toml(task) -> str:
    return f"""version = "2.0"

[metadata]
author_name = "anonymous"
author_email = "anonymous@example.com"
difficulty = "hard"
category = "debugging"
subcategories = ["tool_specific"]
number_of_milestones = 3
codebase_size = "small"
languages = ["cobol", "bash"]
tags = ["cobol", "gnucobol", "fixed-width", "reconciliation"]
expert_time_estimate_min = 120
junior_time_estimate_min = 280

[verifier]
timeout_sec = 900.0

[agent]
timeout_sec = 1800.0

[environment]
allow_internet = false
build_timeout_sec = 900.0
cpus = 2
memory_mb = 4096
storage_mb = 10240
workdir = "/app"

[[steps]]
name = "milestone_1"

[steps.agent]
timeout_sec = 1800.0
[steps.verifier]
timeout_sec = 900.0
[[steps]]
name = "milestone_2"

[steps.agent]
timeout_sec = 1800.0
[steps.verifier]
timeout_sec = 900.0
[[steps]]
name = "milestone_3"

[steps.agent]
timeout_sec = 1800.0
[steps.verifier]
timeout_sec = 900.0
"""


def docs(task) -> dict[str, str]:
    return {
        "record_layouts.md": f"""# Fixed-Width Layouts

Source: type 1, record_id 12, account 8, {task['category']} 3, amount 10, source_date 8, status 1, branch 4.

Action: type 1, record_id 12, account 8, {task['category']} 3, amount 10, action_date 8, reason 3, branch 4.
""",
        "operations.md": f"The nightly {task['domain']} clearing job must reject closed calendar dates and preserve action ordering in reports.\n",
        "runbook.md": f"Run `/app/scripts/run_batch.sh` after fixing `/app/src/{task['program']}.cbl`.\n",
        "support_matrix.md": f"Supported categories: {', '.join(task['allowed'])}. Legacy aliases: {', '.join(task['aliases'])}.\n",
        "release_notes.md": "Known issue: current reconciler was left with incomplete key and calendar validation.\n",
    }


def rubric(task) -> str:
    return "\n".join(
        [
            f"Agent fixes the COBOL reconciler logic rather than hardcoding `/app/out/{task['report']}` or `/app/out/{task['summary']}`, +5",
            "Agent matches only on the full record id, account, amount, branch, source status, eligible reason, and allowed canonical category, +5",
            f"Agent normalizes all documented legacy {task['category']} aliases before matching and emits only canonical matched values, +3",
            "Agent reads the calendar file and treats only explicitly OPEN source dates as eligible, +5",
            "Agent enforces action date ordering and rejects closed, missing, unlisted, or malformed source dates, +3",
            "Agent consumes each source row at most once while preserving action input order, +5",
            "Agent writes the exact report schema and keeps unmatched category fields blank, +3",
            "Agent writes matched and unmatched summary counts and positive integer cent totals, +3",
            "Agent hardcodes final output files or bypasses the COBOL application, -5",
            "Agent uses prefix or substring identifiers, ignores branch/account gates, or reuses consumed source rows, -5",
            "Agent treats closed or missing calendar dates as open, emits raw aliases, or changes required status labels/schema, -5",
        ]
    ) + "\n"


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, newline="\n")


def create_zip(task_dir: Path, zip_path: Path) -> None:
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(task_dir.rglob("*")):
            if path.is_file():
                zf.write(path, path.relative_to(task_dir).as_posix())


def build_task(task):
    task_dir = OUT / task["name"]
    if task_dir.exists():
        shutil.rmtree(task_dir)

    write(task_dir / "task.toml", task_toml(task))
    write(task_dir / "environment" / "Dockerfile", dockerfile())
    write(
        task_dir / "environment" / ".dockerignore",
        ".git\n.gitignore\n**/__pycache__/\n**/*.pyc\n**/.pytest_cache/\n**/.mypy_cache/\n**/.ruff_cache/\n**/node_modules/\n",
    )
    write(task_dir / "environment" / "src" / f"{task['program']}.cbl", common_cobol(task, "seed"))
    write(task_dir / "environment" / "scripts" / "run_batch.sh", f"#!/bin/bash\nset -euo pipefail\nmkdir -p /app/build /app/out\ncobc -x -free -O2 -o /app/build/{task['program']} /app/src/{task['program']}.cbl\n/app/build/{task['program']}\n")
    write(task_dir / "environment" / "scripts" / "clean_outputs.sh", "#!/bin/bash\nset -euo pipefail\nrm -rf /app/out/* /app/build/*\n")
    write(task_dir / "environment" / "data" / task["source_file"], record_source(f"{task['sample_prefix']}SAMPLE001", "ACCT0001", task["allowed"][0], 1000, "20260501", task["source_status"], "B001") + "\n")
    write(task_dir / "environment" / "data" / task["action_file"], record_action(f"{task['sample_prefix']}SAMPLE001", "ACCT0001", list(task["aliases"].keys())[0], 1000, "20260502", task["reasons"][0], "B001") + "\n")
    write(task_dir / "environment" / "data" / "README.md", f"Sample fixed-width data for the {task['domain']} reconciler.\n")
    write(task_dir / "environment" / "config" / task["calendar_file"], "20260501=OPEN\n")
    write(task_dir / "environment" / "config" / "job.properties", f"program={task['program']}\nreport={task['report']}\nsummary={task['summary']}\n")
    write(task_dir / "environment" / "config" / "categories.csv", "code,description\n" + "\n".join(f"{code},{code} category" for code in task["allowed"]) + "\n")
    write(task_dir / "environment" / "config" / "reasons.csv", "code,eligible\n" + "\n".join(f"{code},Y" for code in task["reasons"]) + "\n")
    write(
        task_dir / "environment" / "config" / "validation_notes.txt",
        f"Verifier scenarios rewrite {task['source_file']}, {task['action_file']}, and {task['calendar_file']}.\n",
    )
    write(
        task_dir / "environment" / "copybooks" / "README.md",
        "Copybooks reserved for future layout extraction; current layouts are documented under /app/docs.\n",
    )
    write(
        task_dir / "environment" / "scripts" / "validate_layout.sh",
        "#!/bin/bash\nset -euo pipefail\ntest -f /app/docs/record_layouts.md\n",
    )
    write(task_dir / "environment" / "samples" / task["source_file"], (task_dir / "environment" / "data" / task["source_file"]).read_text())
    write(task_dir / "environment" / "samples" / task["action_file"], (task_dir / "environment" / "data" / task["action_file"]).read_text())
    for name, content in docs(task).items():
        write(task_dir / "environment" / "docs" / name, content)

    milestones = [
        (1, instruction_m1, solve1_sh, test_m1_py),
        (2, instruction_m2, solve2_sh, test_m2_py),
        (3, instruction_m3, solve3_sh, test_m3_py),
    ]
    for number, instruction_fn, solve_fn, test_fn in milestones:
        step = task_dir / "steps" / f"milestone_{number}"
        write(step / "instruction.md", instruction_fn(task))
        write(step / "solution" / "solve.sh", solve_sh(task, number))
        write(step / "solution" / f"solve{number}.sh", solve_fn(task))
        write(step / "tests" / "test.sh", test_sh(number))
        write(step / "tests" / f"test_m{number}.py", test_fn(task))

    write(OUT / f"{task['name']}_rubric.txt", rubric(task))
    create_zip(task_dir, OUT / f"{task['name']}.zip")


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    for task in TASKS:
        build_task(task)


if __name__ == "__main__":
    main()
