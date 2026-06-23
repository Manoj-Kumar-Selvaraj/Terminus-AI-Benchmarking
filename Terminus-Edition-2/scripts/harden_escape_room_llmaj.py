#!/usr/bin/env python3
"""Targeted LLMaJ hardening for go-escape-room-booking-refund-matcher."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TASK = ROOT / "go-escape-room-booking-refund-matcher"


def write_lf(path: Path, text: str) -> None:
    path.write_text(text.replace("\r\n", "\n"), encoding="utf-8", newline="\n")


def replace_many(text: str, pairs: list[tuple[str, str]]) -> str:
    for old, new in pairs:
        text = text.replace(old, new)
    return text


def fix_instruction_text() -> None:
    m1 = TASK / "steps/milestone_1/instruction.md"
    text = m1.read_text(encoding="utf-8")
    text = replace_many(
        text,
        [
            ("HARD credits are being left unmatched", "HARD refunds are being left unmatched"),
            (" Non-numeric `amount_cents` values make that row ineligible for matching.", ""),
        ],
    )
    write_lf(m1, text)

    m3 = TASK / "steps/milestone_3/instruction.md"
    text = m3.read_text(encoding="utf-8")
    text = replace_many(
        text,
        [
            ("dated credit batches", "dated refund batches"),
            ("A credit can match", "A refund can match"),
            ("same credit", "same refund"),
            ("matches the same credit", "matches the same refund"),
        ],
    )
    write_lf(m3, text)


def fix_test_wording(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    text = replace_many(
        text,
        [
            ("credit_rows", "refund_rows"),
            ("credit reconciliation CLI", "refund reconciliation CLI"),
            ("dated credit scenario", "dated refund scenario"),
            ("HARD credits", "HARD refunds"),
            ("HARD credit", "HARD refund"),
            ("A credit", "A refund"),
            ("a credit", "a refund"),
            ("credit room_tiers", "refund room_tiers"),
            ("credit date", "refund date"),
            ("credit whose date", "refund whose date"),
            ("credit with an empty", "refund with an empty"),
            ("credit must", "refund must"),
        ],
    )
    write_lf(path, text)


def add_m2_unmatched_trim_test() -> None:
    path = TASK / "steps/milestone_2/tests/test_m2.py"
    text = path.read_text(encoding="utf-8")
    if "test_unmatched_alias_report_trims_identifier_fields" in text:
        return
    block = '''

    def test_unmatched_alias_report_trims_identifier_fields(self):
        """Unmatched refund rows must trim booking_id and team_id while leaving room_tier blank."""
        write_inputs(
            [" ESC8701 , CUST8701 , 500 , COMPLETED , EASY "],
            [" ESC8701 , CUST8701 , 600 , EA "],
        )
        rows, _ = run_program()
        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["booking_id"] == "ESC8701"
        assert rows[0]["team_id"] == "CUST8701"
        assert rows[0]["room_tier"] == ""
'''
    marker = "\n\n    def test_report_schema_and_refund_input_order_are_stable"
    text = text.replace(marker, block + marker, 1)
    write_lf(path, text)


def fix_m3_docstring_precision() -> None:
    path = TASK / "steps/milestone_3/tests/test_m3.py"
    text = path.read_text(encoding="utf-8")
    text = text.replace(
        '"""Open refund_date gates matching; matched row uses canonical room_tier from latest slot_date."""',
        '"""Open refund_date, room_tier equality, and latest eligible slot_date determine the match."""',
    )
    write_lf(path, text)


def remove_stale_solution_path_replacements() -> None:
    for path in TASK.glob("steps/milestone_*/solution/*.sh"):
        text = path.read_text(encoding="utf-8")
        text = re.sub(
            r"text = text\.replace\(\n\s*'return os\.WriteFile\(\"/app/out/credit_summary\.json\"',\n\s*'return os\.WriteFile\(\"/app/out/escape_refund_summary\.json\"',\n\s*\)\n",
            "",
            text,
            flags=re.MULTILINE,
        )
        write_lf(path, text)


def tighten_second_pass() -> None:
    old_legacy_note = (
        "Internal implementation and verifier helper identifiers may use generic names "
        "such as `Trip`, `Credit`, `Customer`, `PassType`, `source_rows`, or `refund_rows`; "
        "those are internal names only, and the CSV schemas in this instruction are authoritative. "
        "The starter may also use `pass_type` as an internal variable for the CSV `room_tier` column. "
        "Support files such as `config/methods.csv`, `samples/source_edge.csv`, and "
        "`samples/actions_edge.csv` are legacy reference filenames and do not change the "
        "required booking/refund CSV schemas."
    )
    legacy_note = (
        "The starter intentionally uses internal names `Trip`, `Credit`, `Customer`, "
        "`PassType`, `allowedPassType`, and `pass_type` for booking, refund, team, and "
        "`room_tier` concepts; those names are part of the buggy starter implementation, "
        "not the CSV contract. Verifier helpers may use `source_rows` or `refund_rows`; "
        "those are helper names only. Support files `config/methods.csv`, "
        "`samples/source_edge.csv`, and `samples/actions_edge.csv` are legacy reference "
        "filenames and do not change the required booking/refund CSV schemas."
    )
    for path in TASK.glob("steps/milestone_*/instruction.md"):
        text = path.read_text(encoding="utf-8")
        text = text.replace("\n\n" + old_legacy_note + "\n", "\n")
        text = "\n".join(
            line
            for line in text.splitlines()
            if not line.startswith("Internal implementation and verifier helper identifiers may use generic names")
        ) + "\n"
        text = text.replace(
            "room_tier and status comparisons should be case-insensitive",
            "room_tier and source status comparisons should be case-insensitive",
        )
        if legacy_note not in text:
            text = text.rstrip() + "\n\n" + legacy_note + "\n"
        write_lf(path, text)

    m3 = TASK / "steps/milestone_3/instruction.md"
    text = m3.read_text(encoding="utf-8")
    text = text.replace(
        "without reading `/app/config/cutoff_calendar.txt` or requiring calendar dates",
        "without requiring calendar dates",
    )
    if "If both input files use the legacy no-date headers and the calendar file is empty" not in text:
        text = text.replace(
            "When `slot_date` and `refund_date` columns are absent, keep milestone 2 alias normalization, row-position consumption, and matching without requiring calendar dates.",
            "When `slot_date` and `refund_date` columns are absent, keep milestone 2 alias normalization, row-position consumption, and matching without requiring calendar dates. If both input files use the legacy no-date headers and the calendar file is empty, all milestone 2 alias and consumption behavior must still work.",
        )
    if "Concrete milestone 3 edge cases covered by the verifier" not in text:
        text = text.rstrip() + (
            "\n\nConcrete milestone 3 edge cases covered by the verifier include: "
            "with legacy no-date headers and an empty calendar file, duplicate `booking_id` "
            "booking rows are still consumed independently by duplicate refunds; with same "
            "`slot_date` candidates, the earliest booking row is consumed first; only calendar "
            "lines whose second field is `open` count as open; and summary JSON counts and "
            "amounts must exactly reflect the matched and unmatched report rows."
        )
    write_lf(m3, text)

    for path in [
        TASK / "steps/milestone_1/tests/test_m1.py",
        TASK / "steps/milestone_2/tests/test_m2.py",
        TASK / "steps/milestone_3/tests/test_m3.py",
    ]:
        text = path.read_text(encoding="utf-8")
        text = text.replace("bill_rows", "source_rows")
        text = text.replace("action_rows", "refund_rows")
        text = text.replace("credit_rows", "refund_rows")
        write_lf(path, text)

    m3_test = TASK / "steps/milestone_3/tests/test_m3.py"
    text = m3_test.read_text(encoding="utf-8")
    text = text.replace(
        "def test_open_refund_date_and_latest_slot_date_win(self):",
        "def test_one_valid_refund_and_three_invalid_rows_have_expected_status_and_totals(self):",
    )
    text = text.replace(
        "def test_open_refund_date_rejects_invalid_date_and_tier_rows(self):",
        "def test_one_valid_refund_and_three_invalid_rows_have_expected_status_and_totals(self):",
    )
    text = text.replace(
        '"""Only the row satisfying date gates, room_tier equality, latest slot_date, and totals matches."""',
        '"""Only open refund_date <= slot_date with matching room_tier matches; other rows stay unmatched in totals."""',
    )
    text = text.replace(
        '"""Only open refund_date <= slot_date with matching room_tier matches; other rows stay unmatched in totals."""',
        '"""One valid open refund matches; invalid date/tier rows stay unmatched with 1/3 summary totals."""',
    )
    text = text.replace(
        '"""One valid open refund matches; invalid date/tier rows stay unmatched with 1/3 summary totals."""',
        '"""One valid refund matches; date-order, calendar, and tier failures give 1 matched and 3 unmatched."""',
    )
    write_lf(m3_test, text)

    ops = TASK / "environment/docs/operations.md"
    text = ops.read_text(encoding="utf-8")
    text = text.replace(
        "Milestone 3 solution patches may introduce internal date fields such as `RideDate` and `CreditDate` to store the CSV `slot_date` and `refund_date` values. The CSV column names in the milestone instructions are authoritative.",
        "Milestone 3 solution patches store the CSV `slot_date` and `refund_date` values internally. The CSV column names in the milestone instructions are authoritative.",
    )
    write_lf(ops, text)

    solve3 = TASK / "steps/milestone_3/solution/solve3.sh"
    text = solve3.read_text(encoding="utf-8")
    text = replace_many(
        text,
        [
            ("RideDate", "SlotDate"),
            ("HasRideDate", "HasSlotDate"),
            ("rideDate", "slotDate"),
            ("hasRideDate", "hasSlotDate"),
            ("CreditDate", "RefundDate"),
            ("HasCreditDate", "HasRefundDate"),
            ("creditDate", "refundDate"),
            ("hasCreditDate", "hasRefundDate"),
        ],
    )
    write_lf(solve3, text)


def main() -> None:
    fix_instruction_text()
    for test in [
        TASK / "steps/milestone_1/tests/test_m1.py",
        TASK / "steps/milestone_2/tests/test_m2.py",
        TASK / "steps/milestone_3/tests/test_m3.py",
    ]:
        fix_test_wording(test)
    add_m2_unmatched_trim_test()
    fix_m3_docstring_precision()
    remove_stale_solution_path_replacements()
    tighten_second_pass()


if __name__ == "__main__":
    main()
