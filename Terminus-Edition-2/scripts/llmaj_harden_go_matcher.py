#!/usr/bin/env python3
"""Apply LLMaJ-oriented fixes to a Go credit-matcher task (escape-room family)."""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from scaffold_fresh_batch_20260602 import (  # noqa: E402
    fix_alias_legacy_test,
    fix_instructions,
    fix_m3_test_names,
    fix_trim_case_test,
    harden_m3_instruction,
    harden_solve3,
    harden_test_sh,
    inject_legacy_m3_test,
    patch_shipped_data_csv,
    write_lf,
)
from scaffold_go_tasks_from_bike import TASKS  # noqa: E402

LOAD_TYPOS: dict[str, tuple[str, str]] = {}


def spec_for(slug: str) -> dict:
    for s in TASKS:
        if s["slug"] == slug:
            out = dict(s)
            if slug in LOAD_TYPOS:
                out["load_typo"], out["load_fix"] = LOAD_TYPOS[slug]
            return out
    raise KeyError(slug)


def enrich_m1_instruction(path: Path, spec: dict) -> None:
    sid, cid, col = spec["source_id"], spec["customer_id"], spec["category_col"]
    src_schema = f"{sid},{cid},amount_cents,status,{col}"
    act_schema = f"{sid},{cid},amount_cents,{col}"
    header = f"{sid},{cid},{col},amount_cents,status"
    text = path.read_text(encoding="utf-8")
    block = (
        f"Input CSV headers: `{spec['source_file']}` uses `{src_schema}`; "
        f"`{spec['action_file']}` uses `{act_schema}`. "
        f"The report CSV header must be exactly `{header}`. "
        f"Non-numeric `amount_cents` values make that row ineligible for matching. "
        f"Internal Go types may use legacy field names (see `environment/docs/operations.md`); "
        f"CSV column names in this instruction are authoritative."
    )
    if "The report CSV header must be exactly" not in text:
        text = text.replace(
            "The report `status` column must use only the exact strings `MATCHED` and `UNMATCHED`.",
            block + "\n\nThe report `status` column must use only the exact strings `MATCHED` and `UNMATCHED`.",
        )
    path.write_text(text, encoding="utf-8")


def enrich_m3_instruction(path: Path, spec: dict) -> None:
    sd, ad = spec["source_date"], spec["action_date"]
    text = path.read_text(encoding="utf-8")
    date_block = (
        f"Dated inputs append `{sd}` as the last column on `{spec['source_file']}` and "
        f"`{ad}` as the last column on `{spec['action_file']}` when present. "
        f"Duplicate `{spec['source_id']}` rows are separate consumable source records by row position. "
        f"When multiple unused sources qualify for one {spec['action']}, choose the source with the "
        f"latest `{sd}`; ties on `{sd}` break to the earliest source row in file order. "
    )
    if f"append `{sd}`" not in text:
        text = text.replace("For this milestone, input files may include", date_block + "For this milestone, input files may include", 1)
    tail = (
        f"Milestone 3 output keeps report columns `{spec['source_id']},{spec['customer_id']},"
        f"{spec['category_col']},amount_cents,status` and status values `MATCHED`/`UNMATCHED` only."
    )
    if "Milestone 3 output keeps report columns" not in text:
        text = text.rstrip() + "\n\n" + tail + "\n"
    path.write_text(text, encoding="utf-8")


def fix_m3_tests_names_and_docs(dest: Path, spec: dict) -> None:
    path = dest / "steps/milestone_3/tests/test_m3.py"
    text = path.read_text(encoding="utf-8")
    text = text.replace("ESCS =", "SOURCE_FILE =")
    text = text.replace("ESCS.write_text", "SOURCE_FILE.write_text")
    text = text.replace("for action rows", f"for {spec['actions']}")
    text = text.replace("action rows", spec["actions"])
    text = re.sub(
        r'"""Open action dates should gate matching and the latest eligible source date should win\."""',
        f'"""Open {spec["action_date"]} gates matching; matched row uses canonical {spec["category_col"]} from latest {spec["source_date"]}."""',
        text,
    )
    path.write_text(text, encoding="utf-8")


def fix_solve3_date_field_names(dest: Path, spec: dict) -> None:
    """Use domain date field names in solve3 patch (SlotDate not RideDate)."""
    sd_camel = "".join(p.capitalize() for p in spec["source_date"].split("_"))
    ad_camel = "".join(p.capitalize() for p in spec["action_date"].split("_"))
    sd_var = spec["source_date"]
    ad_var = spec["action_date"]
    for solve3 in dest.glob("steps/milestone_3/solution/solve3.sh"):
        text = solve3.read_text(encoding="utf-8")
        text = text.replace("RideDate  string", f"{sd_camel}  string")
        text = text.replace("HasRideDate bool", f"Has{sd_camel} bool")
        text = text.replace("RideDate:", f"{sd_camel}:")
        text = text.replace("HasRideDate:", f"Has{sd_camel}:")
        text = text.replace("trip.RideDate", f"trip.{sd_camel}")
        text = text.replace("hasRideDate", f"has{sd_camel}")
        text = text.replace("rideDate", sd_var)
        text = text.replace("dueDate", sd_var)
        text = text.replace("CreditDate", ad_camel)
        text = text.replace("HasCreditDate", f"Has{ad_camel}")
        text = text.replace("hasCreditDate", f"has{ad_camel}")
        text = text.replace("creditDate", ad_var)
        text = text.replace("credit.CreditDate", f"credit.{ad_camel}")
        if "RideDate  string" in text:
            text = text.replace('"RideDate  string" not in text', f'"{sd_camel}  string" not in text')
        solve3.write_text(text, encoding="utf-8")


def add_m1_unmatched_trim_test(dest: Path, spec: dict) -> None:
    path = dest / "steps/milestone_1/tests/test_m1.py"
    text = path.read_text(encoding="utf-8")
    if "test_unmatched_report_trims_identifier_fields" in text:
        return
    p = spec["prefix"]
    col = spec["category_col"]
    c0 = spec["cats"][0]
    sid, cid = spec["source_id"], spec["customer_id"]
    block = f'''
    def test_unmatched_report_trims_identifier_fields(self):
        """Unmatched report rows must trim {sid} and {cid} output fields."""
        write_inputs(
            [" {p}7701 , CUST7701 , 500 , COMPLETED , {c0} "],
            [" {p}7702 , CUST7702 , 500 , {c0} "],
        )
        rows, _ = run_program()
        assert len(rows) == 2
        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["{sid}"] == "{p}7701"
        assert rows[0]["{cid}"] == "CUST7701"
        assert rows[0]["{col}"] == ""
        assert rows[1]["{sid}"] == "{p}7702"

'''
    if "class TestMilestone1:" not in text:
        return
    text = text.rstrip() + "\n" + block
    path.write_text(text, encoding="utf-8")


def add_m3_header_status_test(dest: Path, spec: dict) -> None:
    path = dest / "steps/milestone_3/tests/test_m3.py"
    text = path.read_text(encoding="utf-8")
    if "test_milestone3_report_header_and_status_vocabulary" in text:
        return
    header = f"{spec['source_id']},{spec['customer_id']},{spec['category_col']},amount_cents,status"
    p = spec["prefix"]
    a0 = spec["aliases"][0][0]
    c0 = spec["cats"][0]
    block = f'''
    def test_milestone3_report_header_and_status_vocabulary(self):
        """Milestone 3 keeps the same report schema and MATCHED/UNMATCHED status labels."""
        write_legacy_inputs(
            ["{p}0001,CUST0001,100,COMPLETED,{c0}"],
            ["{p}0001,CUST0001,100,{a0}"],
        )
        rows, _ = run_program()
        with REPORT.open(newline="") as handle:
            assert handle.readline().strip() == "{header}"
        assert {{row["status"] for row in rows}} <= {{"MATCHED", "UNMATCHED"}}

'''
    if "def write_legacy_inputs" not in text:
        inject_legacy_m3_test(path, spec)
        text = path.read_text(encoding="utf-8")
    marker = "class TestMilestone3:"
    idx = text.index(marker)
    end = text.index("\n    def ", idx + len(marker))
    text = text[:end] + block + text[end:]
    path.write_text(text, encoding="utf-8")


def fix_operations_doc(dest: Path, spec: dict) -> None:
    path = dest / "environment/docs/operations.md"
    sd, ad = spec["source_date"], spec["action_date"]
    extra = (
        f"\n\nMilestone 3 optional date columns map to internal `{sd}` / `{ad}` fields "
        f"when parsing `{spec['source_file']}` and `{spec['action_file']}`."
    )
    text = path.read_text(encoding="utf-8")
    if sd not in text:
        text = text.rstrip() + extra + "\n"
        write_lf(path, text)


def fix_support_matrix_title(dest: Path, spec: dict) -> None:
    path = dest / "environment/docs/support_matrix.md"
    if not path.is_file():
        return
    text = path.read_text(encoding="utf-8")
    col = spec["category_col"]
    text = text.replace("# Support matrix", f"# {col} support matrix")
    text = text.replace("pass/method", col)
    path.write_text(text, encoding="utf-8")


def harden(slug: str) -> None:
    spec = spec_for(slug)
    dest = ROOT / slug
    harden_solve3(dest / "steps/milestone_3/solution/solve3.sh", spec)
    harden_m3_instruction(dest / "steps/milestone_3/instruction.md", spec)
    enrich_m3_instruction(dest / "steps/milestone_3/instruction.md", spec)
    enrich_m1_instruction(dest / "steps/milestone_1/instruction.md", spec)
    patch_shipped_data_csv(dest, spec)
    fix_instructions(dest, spec)
    fix_alias_legacy_test(dest, spec)
    fix_m3_tests_names_and_docs(dest, spec)
    fix_m3_test_names(dest, spec)
    inject_legacy_m3_test(dest / "steps/milestone_3/tests/test_m3.py", spec)
    add_m3_header_status_test(dest, spec)
    add_m1_unmatched_trim_test(dest, spec)
    fix_operations_doc(dest, spec)
    fix_support_matrix_title(dest, spec)
    for test_sh in dest.glob("steps/milestone_*/tests/test.sh"):
        harden_test_sh(test_sh)
    # Ensure M2/M3 tests use SOURCE_FILE not ESCS
    for milestone in (2, 3):
        p = dest / f"steps/milestone_{milestone}/tests/test_m{milestone}.py"
        if p.is_file():
            t = p.read_text(encoding="utf-8")
            t = t.replace("ESCS =", "SOURCE_FILE =").replace("ESCS.write_text", "SOURCE_FILE.write_text")
            p.write_text(t, encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("slugs", nargs="+")
    args = ap.parse_args()
    for slug in args.slugs:
        harden(slug)
        print(f"hardened {slug}")


if __name__ == "__main__":
    main()
