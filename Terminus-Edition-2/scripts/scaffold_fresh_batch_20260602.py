#!/usr/bin/env python3
"""Scaffold five fresh Go credit-matcher tasks (unique domains) and apply quality hardening."""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from scaffold_go_tasks_from_bike import (  # noqa: E402
    apply_replacements,
    patch_alias_tests,
    patch_m1_tests,
    scaffold_task,
    write_lf,
)

FRESH_TASKS = [
    {
        "slug": "go-mini-golf-scorecard-credit-matcher",
        "module": "minigolf-reconcile",
        "tag": "mini-golf",
        "title": "mini golf scorecard credit",
        "entity": "scorecard",
        "entities": "scorecards",
        "action": "scorecard credit",
        "actions": "scorecard credits",
        "source_file": "scorecards.csv",
        "action_file": "credits.csv",
        "source_id": "scorecard_id",
        "customer_id": "player_id",
        "category_col": "course_tier",
        "source_date": "play_date",
        "action_date": "credit_date",
        "report": "scorecard_credit_report.csv",
        "summary": "scorecard_credit_summary.json",
        "cats": ("FRONT", "BACK", "FULL"),
        "aliases": (("FR", "FRONT"), ("BK", "BACK"), ("FL", "FULL")),
        "prefix": "MGL",
        "load_typo": "loadScorecardes",
        "load_fix": "loadScorecards",
    },
    {
        "slug": "go-laundromat-cycle-rebate-matcher",
        "module": "laundromat-reconcile",
        "tag": "laundromat",
        "title": "laundromat cycle rebate",
        "entity": "cycle",
        "entities": "cycles",
        "action": "cycle rebate",
        "actions": "cycle rebates",
        "source_file": "cycles.csv",
        "action_file": "rebates.csv",
        "source_id": "cycle_id",
        "customer_id": "customer_id",
        "category_col": "machine_tier",
        "source_date": "cycle_date",
        "action_date": "rebate_date",
        "report": "cycle_rebate_report.csv",
        "summary": "cycle_rebate_summary.json",
        "cats": ("WASH", "DRY", "COMBO"),
        "aliases": (("WS", "WASH"), ("DR", "DRY"), ("CB", "COMBO")),
        "prefix": "LDM",
        "load_typo": "loadCyclees",
        "load_fix": "loadCycles",
    },
    {
        "slug": "go-museum-visit-audio-credit-matcher",
        "module": "museum-reconcile",
        "tag": "museum",
        "title": "museum visit audio credit",
        "entity": "visit",
        "entities": "visits",
        "action": "audio credit",
        "actions": "audio credits",
        "source_file": "visits.csv",
        "action_file": "audio_credits.csv",
        "source_id": "visit_id",
        "customer_id": "patron_id",
        "category_col": "gallery_tier",
        "source_date": "visit_date",
        "action_date": "credit_date",
        "report": "museum_credit_report.csv",
        "summary": "museum_credit_summary.json",
        "cats": ("GENERAL", "SPECIAL", "MEMBER"),
        "aliases": (("GN", "GENERAL"), ("SP", "SPECIAL"), ("MB", "MEMBER")),
        "prefix": "MUS",
        "load_typo": "loadVisites",
        "load_fix": "loadVisits",
    },
    {
        "slug": "go-recycling-weighin-rebate-matcher",
        "module": "recycle-reconcile",
        "tag": "recycling",
        "title": "recycling weigh-in rebate",
        "entity": "weighin",
        "entities": "weighins",
        "action": "weigh-in rebate",
        "actions": "weigh-in rebates",
        "source_file": "weighins.csv",
        "action_file": "rebates.csv",
        "source_id": "weighin_id",
        "customer_id": "account_id",
        "category_col": "material_tier",
        "source_date": "weighin_date",
        "action_date": "rebate_date",
        "report": "weighin_rebate_report.csv",
        "summary": "weighin_rebate_summary.json",
        "cats": ("METAL", "PAPER", "GLASS"),
        "aliases": (("MT", "METAL"), ("PP", "PAPER"), ("GL", "GLASS")),
        "prefix": "RCY",
        "load_typo": "loadWeighines",
        "load_fix": "loadWeighins",
    },
    {
        "slug": "go-community-pool-lap-credit-matcher",
        "module": "pool-reconcile",
        "tag": "community-pool",
        "title": "community pool lap credit",
        "entity": "lap",
        "entities": "laps",
        "action": "lap credit",
        "actions": "lap credits",
        "source_file": "laps.csv",
        "action_file": "credits.csv",
        "source_id": "lap_id",
        "customer_id": "swimmer_id",
        "category_col": "lane_tier",
        "source_date": "lap_date",
        "action_date": "credit_date",
        "report": "lap_credit_report.csv",
        "summary": "lap_credit_summary.json",
        "cats": ("SLOW", "MED", "FAST"),
        "aliases": (("SL", "SLOW"), ("MD", "MED"), ("FS", "FAST")),
        "prefix": "POL",
        "load_typo": "loadLapes",
        "load_fix": "loadLaps",
    },
]

TEST_SH_WORKDIR = '''if [ "$PWD" = "/" ]; then
    echo "Error: No working directory set. Please set a WORKDIR in your Dockerfile."
    exit 1
fi

'''
PYTEST_COMMENT = "# Requires pytest-json-ctrf (installed in environment/Dockerfile)\n"


def harden_solve3(path: Path, spec: dict) -> None:
    """Use incremental python patch solve3 (Harbor-safe) instead of full-GO rewrite."""
    template = (
        ROOT / "go-food-truck-rally-voucher-matcher" / "steps/milestone_3/solution/solve3.sh"
    ).read_text(encoding="utf-8")
    text = template.replace("rally_voucher_report.csv", spec["report"]).replace(
        "rally_voucher_summary.json", spec["summary"]
    )
    write_lf(path, text)


def harden_solve1(path: Path, spec: dict) -> None:
    text = path.read_text(encoding="utf-8")
    needle = 'text = path.read_text()\nif "func clean(value string)"'
    insert = (
        f'text = path.read_text()\n'
        f'text = text.replace("{spec["load_typo"]}", "{spec["load_fix"]}")\n'
        f'if "func clean(value string)"'
    )
    if spec["load_typo"] not in text and needle in text:
        text = text.replace(needle, insert, 1)
        path.write_text(text, encoding="utf-8")


def harden_main_go(path: Path, spec: dict) -> None:
    text = path.read_text(encoding="utf-8")
    m = re.search(r"func (load\w+)\(", text)
    if m:
        old = m.group(1)
        text = text.replace(f"func {old}(", f"func {spec['load_typo']}(")
        text = re.sub(rf"\b{re.escape(old)}\(", f"{spec['load_typo']}(", text)
    path.write_text(text, encoding="utf-8")


def harden_test_sh(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    if "WORKDIR" not in text:
        text = text.replace(
            "echo 0 > /logs/verifier/reward.txt\n\n",
            "echo 0 > /logs/verifier/reward.txt\n\n" + TEST_SH_WORKDIR,
            1,
        )
    if "pytest-json-ctrf" not in text:
        text = text.replace("python3 -m pytest", PYTEST_COMMENT + "python3 -m pytest", 1)
    write_lf(path, text)


def harden_m3_instruction(path: Path, spec: dict) -> None:
    text = path.read_text(encoding="utf-8")
    sd, ad = spec["source_date"], spec["action_date"]
    legacy = (
        f"When `{sd}` and `{ad}` columns are absent, keep milestone 2 alias normalization, "
        "consumption, and matching without requiring calendar dates. "
    )
    if legacy.strip() not in text:
        text = text.replace("For this milestone, input files may include", legacy + "For this milestone, input files may include", 1)
    path.write_text(text, encoding="utf-8")


def patch_shipped_data_csv(dest: Path, spec: dict) -> None:
  sid, cid, col = spec["source_id"], spec["customer_id"], spec["category_col"]
  src = dest / "environment" / "data" / spec["source_file"]
  act = dest / "environment" / "data" / spec["action_file"]
  if src.exists():
      lines = src.read_text(encoding="utf-8").splitlines()
      lines[0] = f"{sid},{cid},amount_cents,status,{col}"
      lines[1:] = [re.sub(r",ST-\d+,", ",", ln) for ln in lines[1:]]
      write_lf(src, "\n".join(lines) + "\n")
  if act.exists():
      lines = act.read_text(encoding="utf-8").splitlines()
      lines[0] = f"{sid},{cid},amount_cents,{col}"
      lines[1:] = [re.sub(r",ST-\d+,", ",", ln) for ln in lines[1:]]
      write_lf(act, "\n".join(lines) + "\n")


def escape_domain_replacements(text: str, spec: dict) -> str:
    """Map escape-room fixture names to the fresh task domain."""
    c0, c1, c2 = spec["cats"]
    a0, a1, a2 = (alias for alias, _ in spec["aliases"])
    action_word = spec["action"].split()[-1]
    pairs = [
        ("escape_refund_report.csv", spec["report"]),
        ("escape_refund_summary.json", spec["summary"]),
        ("bookings.csv", spec["source_file"]),
        ("refunds.csv", spec["action_file"]),
        ("booking_id", spec["source_id"]),
        ("team_id", spec["customer_id"]),
        ("room_tier", spec["category_col"]),
        ("slot_date", spec["source_date"]),
        ("refund_date", spec["action_date"]),
        ("ESCS =", "SOURCE_FILE ="),
        ("ESCS.write_text", "SOURCE_FILE.write_text"),
        ("ESC", spec["prefix"]),
        ("EASY", c0),
        ("HARD", c1),
        ("VIP", c2),
        ("EA", a0),
        ("HD", a1),
        ("VP", a2),
        ("refund reconciliation", f"{action_word} reconciliation"),
        ("refund", action_word),
        ("booking", spec["entity"]),
        ("bookings", spec["entities"]),
    ]
    for old, new in sorted(pairs, key=lambda item: len(item[0]), reverse=True):
        text = text.replace(old, new)
    return text


def fix_instructions(dest: Path, spec: dict) -> None:
    """Remove stale station_id schema text and align alias codes with tests."""
    a0, a1, a2 = (alias for alias, _ in spec["aliases"])
    sid, cid = spec["source_id"], spec["customer_id"]
    col = spec["category_col"]
    src_schema = f"{sid},{cid},amount_cents,status,{col}"
    act_schema = f"{sid},{cid},amount_cents,{col}"
    for path in dest.glob("steps/milestone_*/instruction.md"):
        text = path.read_text(encoding="utf-8")
        text = text.replace("station_id,", "")
        text = text.replace(",station_id", "")
        text = text.replace(f", {sid}, station_id, amount", f", {sid}, {cid}, amount")
        text = text.replace(f"{sid},player_id,station_id,", f"{sid},{cid},")
        text = text.replace(f"{sid},player_id,station_id,", f"{sid},{cid},")
        text = text.replace(
            f"`scorecards.csv`: `{sid},player_id,station_id,amount_cents,status,{col}`",
            f"`{spec['source_file']}`: `{src_schema}`",
        )
        text = text.replace(
            f"`credits.csv`: `{sid},player_id,station_id,amount_cents,{col}`",
            f"`{spec['action_file']}`: `{act_schema}`",
        )
        text = text.replace("scorecards.csv", spec["source_file"])
        text = text.replace("/app/data/credits.csv", f"/app/data/{spec['action_file']}")
        text = text.replace("`credits.csv`", f"`{spec['action_file']}`")
        # Avoid replacing the *_credits.csv suffix inside an already-correct action filename.
        text = re.sub(
            r"(?<![\w/])credits\.csv",
            spec["action_file"],
            text,
        )
        text = text.replace("`DY`, `MO`, `AN`", f"`{a0}`, `{a1}`, `{a2}`")
        text = text.replace("DY/MO/AN", f"{a0}/{a1}/{a2}")
        text = text.replace("`DY`", f"`{a0}`").replace("`MO`", f"`{a1}`").replace("`AN`", f"`{a2}`")
        write_lf(path, text)


def fix_m3_test_names(dest: Path, spec: dict) -> None:
    a2 = spec["aliases"][2][0]
    path = dest / "steps/milestone_3/tests/test_m3.py"
    text = path.read_text(encoding="utf-8")
    text = text.replace("test_vp_alias", f"test_{a2.lower()}_alias")
    text = text.replace("'VP alias'", f"'{a2} alias'")
    path.write_text(text, encoding="utf-8")


def fix_alias_legacy_test(dest: Path, spec: dict) -> None:
    """Fix escape-room alias codes left in the M2 alias bundle test."""
    a0, a1, a2 = (alias for alias, _ in spec["aliases"])
    c2 = spec["cats"][2]
    path = dest / "steps/milestone_2/tests/test_m2.py"
    text = path.read_text(encoding="utf-8")
    text = text.replace(",hd", f",{a1.lower()}")
    text = text.replace("completed,vip", f"completed,{c2.lower()}")
    path.write_text(text, encoding="utf-8")


def fix_trim_case_test(dest: Path, spec: dict) -> None:
    """Align trim/case test with M1/M2 canonical tiers (not escape-room EASY/VIP)."""
    c0, c1, c2 = spec["cats"]
    for test_py in dest.glob("steps/milestone_*/tests/test_m*.py"):
        text = test_py.read_text(encoding="utf-8")
        if "test_matching_trims_fields" not in text:
            continue
        text = text.replace("completed , easy ", f"completed , {c0.lower()} ")
        text = text.replace("COMPLETED,vip", f"COMPLETED,{c1.lower()}")
        text = text.replace("7200, FULL ", f"7200, {c1} ")
        text = text.replace(f"7200, {c2} ", f"7200, {c1} ")
        text = text.replace('["FRONT", "FULL"]', f'["{c0}", "{c1}"]')
        text = text.replace(f'["{c0}", "{c2}"]', f'["{c0}", "{c1}"]')
        test_py.write_text(text, encoding="utf-8")


def restore_tests_from_escape_room(dest: Path, spec: dict) -> None:
    """Use escape-room verifier tests (correct CSV layout) with domain replacements."""
    esc = ROOT / "go-escape-room-booking-refund-matcher"
    col = spec["category_col"]
    for milestone in (1, 2, 3):
        name = f"test_m{milestone}.py"
        text = (esc / "steps" / f"milestone_{milestone}" / "tests" / name).read_text(encoding="utf-8")
        text = apply_replacements(text, spec)
        text = escape_domain_replacements(text, spec)
        text = text.replace('["pass_type"]', f'["{col}"]')
        text = text.replace('row["pass_type"]', f'row["{col}"]')
        write_lf(dest / "steps" / f"milestone_{milestone}" / "tests" / name, text)
        patch_m1_tests(dest / "steps" / f"milestone_{milestone}" / "tests" / name, spec)
    patch_alias_tests(dest / "steps/milestone_2/tests/test_m2.py", spec)
    patch_alias_tests(dest / "steps/milestone_3/tests/test_m3.py", spec)


def inject_legacy_m3_test(path: Path, spec: dict) -> None:
    text = path.read_text(encoding="utf-8")
    if "write_legacy_inputs" in text:
        return
    col = spec["category_col"]
    a0, a1, a2 = (a for a, _ in spec["aliases"])
    c0, c1, c2 = spec["cats"]
    p = spec["prefix"]
    block = f'''

def write_legacy_inputs(source_rows, action_rows):
    """Pre-date schema: milestone 3 must keep milestone 2 behavior without calendar gates."""
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    SOURCE_FILE.write_text(
        "{spec["source_id"]},{spec["customer_id"]},amount_cents,status,{col}\\n" + "\\n".join(source_rows) + "\\n"
    )
    ACTION_FILE.write_text(
        "{spec["source_id"]},{spec["customer_id"]},amount_cents,{col}\\n" + "\\n".join(action_rows) + "\\n"
    )
    CALENDAR.write_text("")
    REPORT.unlink(missing_ok=True)
    SUMMARY.unlink(missing_ok=True)


'''
    text = text.replace("\n\ndef run_program():", block + "\n\ndef run_program():", 1)
    test_method = f'''
    def test_legacy_schema_without_dates_keeps_prior_alias_and_consumption(self):
        """Pre-date inputs should keep milestone 2 matching without requiring calendar dates."""
        write_legacy_inputs(
            [
                "{p}9001,CUST9001,1200,COMPLETED,{c2}",
                "{p}9001,CUST9001,1200,COMPLETED,{c2}",
                "{p}9002,CUST9002,700,COMPLETED,{c0}",
            ],
            [
                "{p}9001,CUST9001,1200,{a2}",
                "{p}9001,CUST9001,1200,{a2}",
                "{p}9002,CUST9002,700,{a0}",
            ],
        )
        rows, summary = run_program()
        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "MATCHED"]
        assert [row["{col}"] for row in rows] == ["{c2}", "{c2}", "{c0}"]
        assert summary == {{
            "matched_count": 3,
            "matched_amount_cents": 3100,
            "unmatched_count": 0,
            "unmatched_amount_cents": 0,
        }}

'''
    marker = "class TestMilestone3:"
    if marker in text and "test_legacy_schema_without_dates" not in text:
        idx = text.index(marker)
        end = text.index("\n    def ", idx + len(marker))
        text = text[:end] + test_method + text[end:]
    path.write_text(text, encoding="utf-8")


def harden_task(spec: dict) -> None:
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
    for test_sh in dest.glob("steps/milestone_*/tests/test.sh"):
        harden_test_sh(test_sh)


def main() -> None:
    for spec in FRESH_TASKS:
        dest = ROOT / spec["slug"]
        if not dest.exists():
            scaffold_task(spec)
        harden_task(spec)
        print(f"hardened {spec['slug']}")


if __name__ == "__main__":
    main()
