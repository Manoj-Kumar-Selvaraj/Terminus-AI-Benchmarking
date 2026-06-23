#!/usr/bin/env python3
"""LLMaJ-oriented hardening for five pending new tasks (4 credit matchers + rail-yard)."""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from scaffold_fresh_batch_20260602 import (  # noqa: E402
    PYTEST_COMMENT,
    TEST_SH_WORKDIR,
    fix_alias_legacy_test,
    fix_instructions,
    fix_m3_test_names,
    fix_trim_case_test,
    harden_main_go,
    harden_m3_instruction,
    harden_solve1,
    harden_solve3,
    harden_test_sh,
    inject_legacy_m3_test,
    patch_shipped_data_csv,
    restore_tests_from_escape_room,
    write_lf,
)
from scaffold_go_tasks_from_bike import TASKS  # noqa: E402

BATCH_SLUGS = [
    "go-ice-rink-session-credit-matcher",
    "go-photo-booth-print-credit-matcher",
    "go-solar-install-rebate-matcher",
    "go-winery-tasting-refund-matcher",
]

LOAD_TYPOS = {
    "go-ice-rink-session-credit-matcher": ("loadSessiones", "loadSessions"),
    "go-photo-booth-print-credit-matcher": ("loadPrintes", "loadPrints"),
    "go-solar-install-rebate-matcher": ("loadInstalles", "loadInstalls"),
    "go-winery-tasting-refund-matcher": ("loadTastinges", "loadTastings"),
}


def spec_for(slug: str) -> dict:
    for s in TASKS:
        if s["slug"] == slug:
            out = dict(s)
            typo = LOAD_TYPOS.get(slug)
            if typo:
                out["load_typo"], out["load_fix"] = typo
            return out
    raise KeyError(slug)


def enrich_m1_instruction(path: Path, spec: dict) -> None:
    sid, cid, col = spec["source_id"], spec["customer_id"], spec["category_col"]
    src_schema = f"{sid},{cid},amount_cents,status,{col}"
    act_schema = f"{sid},{cid},amount_cents,{col}"
    text = path.read_text(encoding="utf-8")
    header_line = (
        f"`{spec['source_file']}` uses header `{src_schema}`; "
        f"`{spec['action_file']}` uses header `{act_schema}`. "
        f"The report CSV header must be exactly `{sid},{cid},{col},amount_cents,status`."
    )
    if "The report CSV header must be exactly" not in text:
        text = text.replace(
            "The report `status` column must use only the exact strings `MATCHED` and `UNMATCHED`.",
            header_line + "\n\nThe report `status` column must use only the exact strings `MATCHED` and `UNMATCHED`.",
        )
    path.write_text(text, encoding="utf-8")


def enrich_m3_instruction_dates(path: Path, spec: dict) -> None:
    sd, ad = spec["source_date"], spec["action_date"]
    text = path.read_text(encoding="utf-8")
    date_block = (
        f"When date columns are present they append as the last CSV field: `{sd}` on "
        f"`{spec['source_file']}` and `{ad}` on `{spec['action_file']}`. "
        f"Without those columns, milestone 2 alias normalization and consumption still apply. "
    )
    if f"`{sd}` on" not in text:
        text = text.replace("For this milestone, input files may include", date_block + "For this milestone, input files may include", 1)
    extra = (
        f"Milestone 3 report output keeps the same columns and `MATCHED`/`UNMATCHED` "
        f"status vocabulary as milestones 1 and 2 (`{spec['report']}` schema unchanged)."
    )
    if "Milestone 3 report output keeps" not in text:
        text = text.rstrip() + "\n\n" + extra + "\n"
    path.write_text(text, encoding="utf-8")


def fix_test_docstrings(dest: Path, spec: dict) -> None:
    action_word = spec["actions"]
    entity = spec["entities"]
    for path in dest.glob("steps/milestone_*/tests/test_m*.py"):
        text = path.read_text(encoding="utf-8")
        text = text.replace("for action rows", f"for {action_word}")
        text = text.replace("action rows", action_word)
        text = text.replace("action row", spec["action"])
        text = text.replace(
            "Open action dates should gate matching and the latest eligible source date should win.",
            "Open credit dates gate matching; among eligible sources the latest source date wins.",
        )
        text = text.replace(
            '"""Date gates and latest eligible source-row selection for action rows."""',
            f'"""Date gates and latest eligible {entity} selection for {action_word}."""',
        )
        path.write_text(text, encoding="utf-8")


def add_m3_schema_test(path: Path, spec: dict) -> None:
    text = path.read_text(encoding="utf-8")
    if "test_milestone3_report_header_and_status_vocabulary" in text:
        return
    sid, cid, col = spec["source_id"], spec["customer_id"], spec["category_col"]
    header = f"{sid},{cid},{col},amount_cents,status"
    block = f'''
    def test_milestone3_report_header_and_status_vocabulary(self):
        """Milestone 3 keeps the same report schema and MATCHED/UNMATCHED status labels."""
        write_legacy_inputs(
            ["{spec["prefix"]}0001,CUST0001,100,COMPLETED,{spec["cats"][0]}"],
            ["{spec["prefix"]}0001,CUST0001,100,{spec["aliases"][0][0]}"],
        )
        rows, _ = run_program()
        with REPORT.open(newline="") as handle:
            assert handle.readline().strip() == "{header}"
        assert {{row["status"] for row in rows}} <= {{"MATCHED", "UNMATCHED"}}

'''
    marker = "class TestMilestone3:"
    if marker in text:
        idx = text.index(marker)
        end = text.index("\n    def ", idx + len(marker))
        text = text[:end] + block + text[end:]
        path.write_text(text, encoding="utf-8")


def harden_credit_matcher(spec: dict) -> None:
    dest = ROOT / spec["slug"]
    harden_main_go(dest / "environment/cmd/reconcile/main.go", spec)
    harden_solve1(dest / "steps/milestone_1/solution/solve1.sh", spec)
    harden_solve3(dest / "steps/milestone_3/solution/solve3.sh", spec)
    harden_m3_instruction(dest / "steps/milestone_3/instruction.md", spec)
    patch_shipped_data_csv(dest, spec)
    fix_instructions(dest, spec)
    restore_tests_from_escape_room(dest, spec)
    fix_trim_case_test(dest, spec)
    fix_alias_legacy_test(dest, spec)
    inject_legacy_m3_test(dest / "steps/milestone_3/tests/test_m3.py", spec)
    fix_m3_test_names(dest, spec)
    fix_test_docstrings(dest, spec)
    enrich_m1_instruction(dest / "steps/milestone_1/instruction.md", spec)
    enrich_m3_instruction_dates(dest / "steps/milestone_3/instruction.md", spec)
    add_m3_schema_test(dest / "steps/milestone_3/tests/test_m3.py", spec)
    for test_sh in dest.glob("steps/milestone_*/tests/test.sh"):
        harden_test_sh(test_sh)


def harden_rail_yard() -> None:
    dest = ROOT / "go-rail-yard-freight-hold-release"
    dc = ROOT / "go-datacenter-rack-hold-release"
    pairs = [
        ("rack_release", "freight_release"),
        ("asset_id", "car_id"),
        ("aisle_id", "yard_id"),
        ("access_tier", "cargo_class"),
        ("rack", "track"),
        ("LOCKED", "HELD"),
        ("DECOMM", "RELEASE"),
        ("MIGRATE", "RECALL"),
        ("HOT", "HAZ"),
        ("WARM", "DRY"),
        ("COLD", "REF"),
        ("datacenter rack", "rail yard freight"),
    ]
    for milestone in (1, 2, 3):
        for name in ("test_m1.py", "test_m2.py", "test_m3.py"):
            src = dc / "steps" / f"milestone_{milestone}" / "tests" / name
            if not src.is_file():
                continue
            text = src.read_text(encoding="utf-8")
            for old, new in pairs:
                text = text.replace(old, new)
            write_lf(dest / "steps" / f"milestone_{milestone}" / "tests" / name, text)
        harden_test_sh(dest / f"steps/milestone_{milestone}/tests/test.sh")

    for path in dest.glob("steps/milestone_*/instruction.md"):
        text = path.read_text(encoding="utf-8")
        if "milestone_1" in path.parts:
            text = re.sub(
                r", using `/app/config/windows\.csv` for the active realtime window rules\.?",
                "",
                text,
            )
            text = re.sub(
                r" using `/app/config/windows\.csv` for the active realtime window rules\.?",
                "",
                text,
            )
        extra = (
            "Window scope uses `yard_id` in `/app/config/windows.csv` (`yard_id,open_ts,close_ts,state`). "
            "Milestone 3 report columns stay `release_id,hold_id,car_id,yard_id,cargo_class,amount,reason,status` "
            "with only `MATCHED` or `UNMATCHED` in the status column."
        )
        if "Window scope uses" not in text and "milestone_3" in path.parts:
            text = text.rstrip() + "\n\n" + extra + "\n"
        write_lf(path, text)


def main() -> None:
    for slug in BATCH_SLUGS:
        spec = spec_for(slug)
        harden_credit_matcher(spec)
        print(f"hardened {slug}")
    harden_rail_yard()
    print("hardened go-rail-yard-freight-hold-release")


if __name__ == "__main__":
    main()
