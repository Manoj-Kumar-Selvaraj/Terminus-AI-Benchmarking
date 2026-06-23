#!/usr/bin/env python3
"""Scaffold new COBOL milestone tasks from cobol-marina-docking-fee-reversal."""
from __future__ import annotations

import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "cobol-marina-docking-fee-reversal"

M1_EXTRA = (
    " The `status` column must contain exactly `MATCHED` for matched rows or "
    "`UNMATCHED` for unmatched rows. Unmatched rows emit an empty string for the "
    "`{category_col}` column (two consecutive commas in the CSV, not whitespace-padded). "
    "Matched rows emit the canonical source {category_col} and preserve the action "
    "reason in the `reason` column. Trim trailing spaces from fixed-width record id "
    "and account fields when writing CSV output."
)

M3_CALENDAR = (
    "Source dates are eligible only when the source date is numeric, the same date "
    "appears in the calendar file, and the calendar state equals `OPEN` when compared "
    "case-insensitively (for example `open`, `Open`, and `oPeN` are all eligible). "
    "Closed, missing, unlisted, or non-numeric source dates are ineligible even if "
    "the calendar file lists them."
)

LATEST_TEST = '''def test_latest_source_date_wins_when_multiple_rows_qualify():
    """Latest open source date must win even when an older row appears first in the file."""
    compile_program()
    write_inputs(
        [
            src("{prefix}LAT0000001", "ACCT7001", "{c0}", 500, "20260801", branch="BG01"),
            src("{prefix}LAT0000001", "ACCT7001", "{c1}", 1000, "20260805", branch="BG01"),
            src("{prefix}LAT0000001", "ACCT7001", "{c1}", 700, "20260803", branch="BG01"),
        ],
        [
            action("{prefix}LAT0000001", "ACCT7001", "{a1}", 1000, "20260810", "{r0}", branch="BG01"),
            action("{prefix}LAT0000001", "ACCT7001", "{a1}", 700, "20260810", "{r0}", branch="BG01"),
            action("{prefix}LAT0000001", "ACCT7001", "{a0}", 500, "20260810", "{r0}", branch="BG01"),
        ],
        ["20260801=OPEN", "20260803=OPEN", "20260805=OPEN", "20260810=OPEN"],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "MATCHED"]
    assert summary == {{
        "matched_count": 3,
        "matched_amount_cents": 2200,
        "unmatched_count": 0,
        "unmatched_amount_cents": 0,
    }}


def test_same_source_date_tie_prefers_earliest_input_row():
    """When source dates tie, the earliest source input row must be consumed first."""
    compile_program()
    write_inputs(
        [
            src("{prefix}TIE0000001", "ACCT7101", "{c0}", 500, "20260805", branch="BG01"),
            src("{prefix}TIE0000001", "ACCT7101", "{c0}", 700, "20260805", branch="BG01"),
            src("{prefix}TIE0000001", "ACCT7101", "{c2}", 900, "20260808", branch="BG01"),
        ],
        [
            action("{prefix}TIE0000001", "ACCT7101", "{a2}", 900, "20260810", "{r0}", branch="BG01"),
            action("{prefix}TIE0000001", "ACCT7101", "{a0}", 500, "20260810", "{r0}", branch="BG01"),
            action("{prefix}TIE0000001", "ACCT7101", "{a0}", 700, "20260810", "{r0}", branch="BG01"),
        ],
        ["20260805=OPEN", "20260808=OPEN", "20260810=OPEN"],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "MATCHED"]
    assert summary["matched_count"] == 3
    assert summary["matched_amount_cents"] == 2100


def test_duplicate_record_id_rows_are_consumed_by_position():
    """Two source rows with the same record id must be independently consumable by amount."""
    compile_program()
    write_inputs(
        [
            src("{prefix}POS000001", "ACCT9001", "{c0}", 500, "20260810", branch="BX01"),
            src("{prefix}POS000001", "ACCT9001", "{c0}", 700, "20260810", branch="BX01"),
        ],
        [
            action("{prefix}POS000001", "ACCT9001", "{c0}", 500, "20260811", "{r0}", branch="BX01"),
            action("{prefix}POS000001", "ACCT9001", "{c0}", 700, "20260811", "{r0}", branch="BX01"),
        ],
        ["20260810=OPEN", "20260811=OPEN"],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
    assert summary == {{
        "matched_count": 2,
        "matched_amount_cents": 1200,
        "unmatched_count": 0,
        "unmatched_amount_cents": 0,
    }}


def test_calendar_open_state_is_case_insensitive():
    """Mixed-case OPEN calendar states must still allow eligible source dates."""
    compile_program()
    write_inputs(
        [src("{prefix}CASE000001", "ACCT9002", "{c0}", 500, "20260901", branch="BX02")],
        [action("{prefix}CASE000001", "ACCT9002", "{a0}", 500, "20260902", "{r0}", branch="BX02")],
        ["20260901=Open", "20260902=OPEN"],
    )
    rows, summary = run_program()

    assert rows[0]["status"] == "MATCHED"
    assert rows[0]["{category_col}"] == "{c0}"
    assert summary["matched_count"] == 1


'''

TASKS = [
    {
        "slug": "cobol-bowling-league-fee-reversal",
        "replacements": [
            ("cobol-marina-docking-fee-reversal", "cobol-bowling-league-fee-reversal"),
            ("marina docking fee reversal", "bowling league fee reversal"),
            ("docking_reversal_reconcile", "league_fee_reversal_reconcile"),
            ("docking-reversal-reconcile", "league-fee-reversal-reconcile"),
            ("dock_fees.dat", "lane_fees.dat"),
            ("docking_reversal_report", "league_reversal_report"),
            ("docking_reversal_summary", "league_reversal_summary"),
            ("harbor_calendar.txt", "league_calendar.txt"),
            ("berth_type", "lane_type"),
            ("SLP", "STR"),
            ("DRY", "SCR"),
            ("TRN", "COS"),
            ('IF ACT-CAT(1:2) = "SP"', 'IF ACT-CAT(1:2) = "ST"'),
            ('MOVE "SLP" TO CANON-CAT', 'MOVE "STR" TO CANON-CAT'),
            ('IF ACT-CAT(1:2) = "DY"', 'IF ACT-CAT(1:2) = "SC"'),
            ('MOVE "DRY" TO CANON-CAT', 'MOVE "SCR" TO CANON-CAT'),
            ('IF ACT-CAT(1:2) = "TN"', 'IF ACT-CAT(1:2) = "CO"'),
            ('MOVE "TRN" TO CANON-CAT', 'MOVE "COS" TO CANON-CAT'),
            ("H02", "B02"),
            ("H06", "B05"),
            ("H13", "B11"),
            ('SRC-STATUS(I) = "D"', 'SRC-STATUS(I) = "L"'),
            ('status="D"', 'status="L"'),
            ("MR", "BL"),
            ("marina", "bowling league"),
        ],
        "category_col": "lane_type",
        "cats": ("STR", "SCR", "COS"),
        "aliases": ("ST", "SC", "CO"),
        "reason": "B02",
        "prefix": "BL",
    },
    {
        "slug": "cobol-zoo-admission-refund-clearing",
        "replacements": [
            ("cobol-marina-docking-fee-reversal", "cobol-zoo-admission-refund-clearing"),
            ("marina docking fee reversal", "zoo admission refund"),
            ("docking_reversal_reconcile", "zoo_refund_reconcile"),
            ("docking-reversal-reconcile", "zoo-refund-reconcile"),
            ("dock_fees.dat", "admissions.dat"),
            ("reversals.dat", "refunds.dat"),
            ("docking_reversal_report", "zoo_refund_report"),
            ("docking_reversal_summary", "zoo_refund_summary"),
            ("harbor_calendar.txt", "gate_calendar.txt"),
            ("berth_type", "ticket_tier"),
            ("SLP", "ADT"),
            ("DRY", "CHD"),
            ("TRN", "SEN"),
            ('IF ACT-CAT(1:2) = "SP"', 'IF ACT-CAT(1:2) = "AD"'),
            ('MOVE "SLP" TO CANON-CAT', 'MOVE "ADT" TO CANON-CAT'),
            ('IF ACT-CAT(1:2) = "DY"', 'IF ACT-CAT(1:2) = "CH"'),
            ('MOVE "DRY" TO CANON-CAT', 'MOVE "CHD" TO CANON-CAT'),
            ('IF ACT-CAT(1:2) = "TN"', 'IF ACT-CAT(1:2) = "SE"'),
            ('MOVE "TRN" TO CANON-CAT', 'MOVE "SEN" TO CANON-CAT'),
            ("H02", "Z02"),
            ("H06", "Z05"),
            ("H13", "Z14"),
            ('SRC-STATUS(I) = "D"', 'SRC-STATUS(I) = "A"'),
            ('status="D"', 'status="A"'),
            ("MR", "ZO"),
            ("marina", "zoo admission"),
        ],
        "category_col": "ticket_tier",
        "cats": ("ADT", "CHD", "SEN"),
        "aliases": ("AD", "CH", "SE"),
        "reason": "Z02",
        "prefix": "ZO",
    },
    {
        "slug": "cobol-campground-site-deposit-matcher",
        "replacements": [
            ("cobol-marina-docking-fee-reversal", "cobol-campground-site-deposit-matcher"),
            ("marina docking fee reversal", "campground site deposit"),
            ("docking_reversal_reconcile", "camp_deposit_reconcile"),
            ("docking-reversal-reconcile", "camp-deposit-reconcile"),
            ("dock_fees.dat", "site_fees.dat"),
            ("reversals.dat", "deposit_returns.dat"),
            ("docking_reversal_report", "camp_deposit_report"),
            ("docking_reversal_summary", "camp_deposit_summary"),
            ("harbor_calendar.txt", "season_calendar.txt"),
            ("berth_type", "site_class"),
            ("SLP", "TNT"),
            ("DRY", "RV"),
            ("TRN", "CBN"),
            ('IF ACT-CAT(1:2) = "SP"', 'IF ACT-CAT(1:2) = "NT"'),
            ('MOVE "SLP" TO CANON-CAT', 'MOVE "TNT" TO CANON-CAT'),
            ('IF ACT-CAT(1:2) = "DY"', 'IF ACT-CAT(1:2) = "R0"'),
            ('MOVE "DRY" TO CANON-CAT', 'MOVE "RV" TO CANON-CAT'),
            ('IF ACT-CAT(1:2) = "TN"', 'IF ACT-CAT(1:2) = "CB"'),
            ('MOVE "TRN" TO CANON-CAT', 'MOVE "CBN" TO CANON-CAT'),
            ("H02", "C02"),
            ("H06", "C06"),
            ("H13", "C10"),
            ('SRC-STATUS(I) = "D"', 'SRC-STATUS(I) = "G"'),
            ('status="D"', 'status="G"'),
            ("MR", "CG"),
            ("marina", "campground"),
        ],
        "category_col": "site_class",
        "cats": ("TNT", "RV", "CBN"),
        "aliases": ("NT", "R0", "CB"),
        "reason": "C02",
        "prefix": "CG",
    },
    {
        "slug": "cobol-laundromat-load-credit-clearing",
        "replacements": [
            ("cobol-marina-docking-fee-reversal", "cobol-laundromat-load-credit-clearing"),
            ("marina docking fee reversal", "laundromat load credit"),
            ("docking_reversal_reconcile", "laundry_credit_reconcile"),
            ("docking-reversal-reconcile", "laundry-credit-reconcile"),
            ("dock_fees.dat", "machine_loads.dat"),
            ("reversals.dat", "credits.dat"),
            ("docking_reversal_report", "laundry_credit_report"),
            ("docking_reversal_summary", "laundry_credit_summary"),
            ("harbor_calendar.txt", "service_calendar.txt"),
            ("berth_type", "machine_size"),
            ("SLP", "SML"),
            ("DRY", "MDL"),
            ("TRN", "LGE"),
            ('IF ACT-CAT(1:2) = "SP"', 'IF ACT-CAT(1:2) = "SM"'),
            ('MOVE "SLP" TO CANON-CAT', 'MOVE "SML" TO CANON-CAT'),
            ('IF ACT-CAT(1:2) = "DY"', 'IF ACT-CAT(1:2) = "MD"'),
            ('MOVE "DRY" TO CANON-CAT', 'MOVE "MDL" TO CANON-CAT'),
            ('IF ACT-CAT(1:2) = "TN"', 'IF ACT-CAT(1:2) = "LG"'),
            ('MOVE "TRN" TO CANON-CAT', 'MOVE "LGE" TO CANON-CAT'),
            ("H02", "W02"),
            ("H06", "W05"),
            ("H13", "W09"),
            ('SRC-STATUS(I) = "D"', 'SRC-STATUS(I) = "R"'),
            ('status="D"', 'status="R"'),
            ("MR", "LD"),
            ("marina", "laundromat"),
        ],
        "category_col": "machine_size",
        "cats": ("SML", "MDL", "LGE"),
        "aliases": ("SM", "MD", "LG"),
        "reason": "W02",
        "prefix": "LD",
    },
    {
        "slug": "cobol-scooter-ride-surcharge-reversal",
        "replacements": [
            ("cobol-marina-docking-fee-reversal", "cobol-scooter-ride-surcharge-reversal"),
            ("marina docking fee reversal", "scooter ride surcharge reversal"),
            ("docking_reversal_reconcile", "scooter_surcharge_reconcile"),
            ("docking-reversal-reconcile", "scooter-surcharge-reconcile"),
            ("dock_fees.dat", "ride_charges.dat"),
            ("reversals.dat", "surcharge_reversals.dat"),
            ("docking_reversal_report", "scooter_surcharge_report"),
            ("docking_reversal_summary", "scooter_surcharge_summary"),
            ("harbor_calendar.txt", "fleet_calendar.txt"),
            ("berth_type", "zone_code"),
            ("SLP", "CBD"),
            ("DRY", "RES"),
            ("TRN", "UNI"),
            ('IF ACT-CAT(1:2) = "SP"', 'IF ACT-CAT(1:2) = "CB"'),
            ('MOVE "SLP" TO CANON-CAT', 'MOVE "CBD" TO CANON-CAT'),
            ('IF ACT-CAT(1:2) = "DY"', 'IF ACT-CAT(1:2) = "RE"'),
            ('MOVE "DRY" TO CANON-CAT', 'MOVE "RES" TO CANON-CAT'),
            ('IF ACT-CAT(1:2) = "TN"', 'IF ACT-CAT(1:2) = "UN"'),
            ('MOVE "TRN" TO CANON-CAT', 'MOVE "UNI" TO CANON-CAT'),
            ("H02", "S02"),
            ("H06", "S07"),
            ("H13", "S15"),
            ('SRC-STATUS(I) = "D"', 'SRC-STATUS(I) = "Z"'),
            ('status="D"', 'status="Z"'),
            ("MR", "SC"),
            ("marina", "scooter fleet"),
        ],
        "category_col": "zone_code",
        "cats": ("CBD", "RES", "UNI"),
        "aliases": ("CB", "RE", "UN"),
        "reason": "S02",
        "prefix": "SC",
    },
]


def rubric_for(slug: str, category_col: str) -> str:
    return f"""# Rubric 1

Agent inspects `/app/src/` COBOL source, `/app/docs/record_layouts.md`, and output contracts before editing `{slug}`, +2
Agent keeps rewritten COBOL valid for free-format compilation with `cobc -x -free -O2`, +3
Agent parses `record_id` after the one-byte record type prefix without including `S` or `A` in comparisons or CSV output, +5
Agent fixes reconciliation logic instead of hardcoding `/app/out/` report or summary files, +3
Agent enforces milestone 1 matching gates including record id, account, amount, branch, source status, eligible reasons, allowed canonical {category_col} values, and action date ordering, +5
Agent preserves action input order, zero-padded `amount_cents`, exact report columns, and exact `MATCHED` and `UNMATCHED` labels, +3
Agent leaves `{category_col}` blank on every `UNMATCHED` row and emits canonical source `{category_col}` on `MATCHED` rows, +3
Agent preserves action reason text in the report `reason` column for matched and unmatched rows, +3
Agent writes positive integer `key=value` summary lines for matched and unmatched counts and amounts, +3
Agent consumes each source row at most once so duplicate actions cannot reuse the same source row, +5
Agent hardcodes final CSV or summary output instead of repairing the COBOL program, -5

# Rubric 2

Agent normalizes legacy action aliases to canonical {category_col} codes before matching and report output, +5
Agent emits canonical {category_col} values on matched alias rows rather than raw alias codes, +3
Agent preserves milestone 1 blank-unmatched `{category_col}` behavior while adding alias normalization, +3
Agent keeps required output paths and schemas unchanged when extending alias handling, +3
Agent trims trailing spaces from fixed-width identifiers when writing CSV fields, +3
Agent validates alias and consumption behavior against fresh synthetic fixtures, +2
Agent regresses milestone 1 matching gates while implementing alias normalization, -3
Agent tampers with verifier harness files or solution scaffolding to force a pass, -5
Agent repeats failing compile or test commands without adjusting approach after clear errors, -2

# Rubric 3

Agent applies calendar eligibility from the task config calendar file while preserving prior matching gates, +5
Agent treats calendar state `OPEN` case-insensitively and rejects closed, missing, unlisted, or non-numeric source dates, +3
Agent chooses the eligible source row with the latest open source date when multiple unused rows qualify, +5
Agent breaks tied source dates by selecting the earliest source input row, +3
Agent consumes duplicate record ids by source row position rather than blocking all rows that share an id, +3
Agent preserves alias normalization, blank unmatched `{category_col}`, and reason output under calendar gates, +3
Agent verifies latest-date selection with distinct source amounts so first-fit file order cannot pass, +3
Agent validates final report and summary artifacts before finishing milestone 3, +2
Agent treats closed or unlisted calendar dates as open, -5
Agent regresses milestone 1 or 2 behavior while implementing calendar or latest-date logic, -3
"""


def patch_m1_instruction(path: Path, category_col: str) -> None:
    text = path.read_text(encoding="utf-8")
    old = (
        "Write `/app/out/"
    )
    if "Unmatched rows emit" in text:
        return
    needle = "with all amounts counted as positive integer cents.\n\nThe report `status`"
    if needle in text:
        insert = (
            f" with all amounts counted as positive integer cents."
            f"{M1_EXTRA.format(category_col=category_col)}\n"
        )
        text = text.replace(
            "with all amounts counted as positive integer cents.\n\nThe report `status`",
            insert + "\nThe report `status`",
        )
        path.write_text(text, encoding="utf-8")


def patch_m3_instruction(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    old = (
        "Source dates are eligible only when the same date appears in the calendar file "
        "with the literal state `OPEN` compared case-insensitively; closed, missing, "
        "unlisted, or malformed dates are ineligible."
    )
    if old in text:
        text = text.replace(old, M3_CALENDAR)
        path.write_text(text, encoding="utf-8")


def patch_m3_tests(path: Path, spec: dict) -> None:
    text = path.read_text(encoding="utf-8")
    start = text.index("def test_latest_source_date_wins_when_multiple_rows_qualify")
    end = text.index("\ndef test_second_action_stays_unmatched_after_latest_source_row_is_consumed")
    block = LATEST_TEST.format(
        prefix=spec["prefix"],
        c0=spec["cats"][0],
        c1=spec["cats"][1],
        c2=spec["cats"][2],
        a0=spec["aliases"][0],
        a1=spec["aliases"][1],
        a2=spec["aliases"][2],
        r0=spec["reason"],
        category_col=spec["category_col"],
    )
    text = text[:start] + block + text[end:]
    path.write_text(text, encoding="utf-8")


def patch_solve3_upper(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    old = (
        '                      AND (CAL-STATE(CAL-IDX) = "OPEN"\n'
        '                        OR CAL-STATE(CAL-IDX) = "open")'
    )
    new = '                      AND FUNCTION UPPER-CASE(CAL-STATE(CAL-IDX)) = "OPEN"'
    if old in text:
        text = text.replace(old, new)
        path.write_text(text, encoding="utf-8")


def scaffold_task(spec: dict) -> None:
    dest = ROOT / spec["slug"]
    if dest.exists():
        print(f"exists, refreshing post-patches only: {spec['slug']}")
    else:
        shutil.copytree(TEMPLATE, dest)
        for path in dest.rglob("*"):
            if not path.is_file():
                continue
            if path.suffix == ".dat":
                continue
            content = path.read_text(encoding="utf-8", errors="replace")
            for old, new in spec["replacements"]:
                content = content.replace(old, new)
            path.write_text(content, encoding="utf-8")
        old_cbl = dest / "environment" / "src" / "docking_reversal_reconcile.cbl"
        new_name = spec["replacements"][2][1] + ".cbl"
        if old_cbl.exists():
            old_cbl.rename(old_cbl.with_name(new_name))
        print(f"created {spec['slug']}")

    patch_m1_instruction(dest / "steps" / "milestone_1" / "instruction.md", spec["category_col"])
    patch_m3_instruction(dest / "steps" / "milestone_3" / "instruction.md")
    patch_m3_tests(dest / "steps" / "milestone_3" / "tests" / "test_m3.py", spec)
    patch_solve3_upper(dest / "steps" / "milestone_3" / "solution" / "solve3.sh")
    (dest / "rubric.txt").write_text(rubric_for(spec["slug"], spec["category_col"]), encoding="utf-8")


def main() -> None:
    for spec in TASKS:
        scaffold_task(spec)


if __name__ == "__main__":
    main()
