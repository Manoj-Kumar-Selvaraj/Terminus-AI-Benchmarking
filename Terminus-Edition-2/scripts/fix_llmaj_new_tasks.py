#!/usr/bin/env python3
"""Apply strict LLMaJ instruction/test fixes to unrevised new tasks."""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from fix_new_task_oracles import GO_SPECS, RUBY_SPECS  # noqa: E402

M1_NON_NUMERIC_TEST = '''
def test_non_numeric_timestamps_stay_unmatched():
    """Non-numeric {source_ts_col} or {action_ts_col} values must reject matching."""
    build_program()
    write_inputs(
        [["SRC-BAD-TS", "PARTY-1", "S-1", "{cat0}", "10", "bad-ts", "{posted}", "L1"]],
        [["ACT-BAD-TS", "SRC-BAD-TS", "PARTY-1", "S-1", "{cat0}", "10", "20260528140500", "{reason0}", "L1"]],
        [["S-1", "20260528135900", "20260528143000", "OPEN"]],
    )
    rows, summary = run_program()
    assert rows[0]["status"] == "UNMATCHED"
    assert rows[0]["{category_col}"] == ""
    assert summary["matched_count"] == 0
'''

M3_NON_NUMERIC_TEST = '''
def test_non_numeric_release_timestamp_stays_unmatched():
    """A correction with non-numeric {action_ts_col} must stay unmatched even inside an OPEN window."""
    build_program()
    write_inputs(
        [["SRC-REL-BAD", "PARTY-1", "S-1", "{cat2}", "15", "20260528140000", "{posted}", "L1"]],
        [["ACT-REL-BAD", "SRC-REL-BAD", "PARTY-1", "S-1", "{alias2}", "15", "bad-ts", "{reason0}", "L1"]],
        [["S-1", "20260528135900", "20260528143000", "OPEN"]],
    )
    rows, summary = run_program()
    assert rows[0]["status"] == "UNMATCHED"
    assert rows[0]["{category_col}"] == ""
    assert summary["matched_count"] == 0
'''


def load_tasks() -> list[str]:
    text = (ROOT / "new_tasks.txt").read_text(encoding="utf-8-sig")
    return [l.strip() for l in text.splitlines() if l.strip() and not l.strip().startswith("#")]


def write_lf(path: Path, content: str) -> None:
    path.write_text(content.replace("\r\n", "\n"), encoding="utf-8", newline="\n")


def cats_text(cats: list[str]) -> str:
    return ", ".join(f"`{c}`" for c in cats)


def fix_m1_instruction(path: Path, spec: dict, lang: str) -> bool:
    if not path.is_file():
        return False
    text = path.read_text(encoding="utf-8")
    col = spec["category_col"]
    cats_m1 = cats_text(spec["cats_m1"])
    cat_third = spec["cats"][2]
    posted = spec["posted_status"]
    reasons = ", ".join(f"`{r}`" for r in spec["reasons"])
    source_ts = spec["source_ts_col"]
    action_ts = spec["action_ts_col"]
    report = spec["report_file"]
    summary = spec["summary_file"]
    impl = "/app/cmd/reconcile/main.go" if lang == "go" else "/app/app/reconcile.rb"
    source = spec["source_file"]
    action = spec["action_file"]

    id_fields = f"`{spec['source_id_col']}`, `{spec['party_col']}`, `{spec['scope_col']}`, `{spec['loc_col']}`, and `amount`"

    # strip windows from M1 opener
    text = re.sub(
        r", using `/app/config/windows\.csv` for the active realtime window rules",
        "",
        text,
    )
    text = re.sub(
        r"using `/app/config/windows\.csv` for the active realtime window rules\. ",
        "",
        text,
    )

    m1_block = (
        f"Milestone 1 is about the exact reconciliation contract without legacy aliases or realtime window rules. "
        f"A correction can match only when the full {id_fields} all match, the source status is the literal `{posted}`, "
        f"the correction reason is {reasons}, the `{col}` field is one of the canonical values {cats_m1} on both sides "
        f"after trimming and case folding, both timestamps are numeric 14-digit UTC values, the correction timestamp "
        f"`{action_ts}` is on or after the source timestamp `{source_ts}`, and the source row has not already been consumed. "
        f"Source or correction rows whose `{col}` is anything else, including `{cat_third}` and legacy alias codes, are ineligible in this milestone. "
        f"Non-numeric `{source_ts}` or `{action_ts}` values make the row ineligible.\n\n"
        f"Preserve correction input order, use `MATCHED` or `UNMATCHED` only, leave `{col}` blank for unmatched rows, "
        f"and write positive matched and unmatched summary totals.\n\n"
        f"Write `/app/out/{report}` and `/app/out/{summary}` with the schema documented in this milestone. "
        f"The reconciler lives in `{impl}` and reads `/app/data/{source}` and `/app/data/{action}`.\n\n"
        f"The report `status` column must use only the exact strings `MATCHED` and `UNMATCHED`."
    )

    if "Milestone 1 is about the exact reconciliation contract" in text:
        text = re.sub(
            r"Milestone 1 is about the exact reconciliation contract.*?(?=\n\nWrite `/app/out/|\Z)",
            m1_block,
            text,
            count=1,
            flags=re.DOTALL,
        )
    else:
        # replace body after first paragraph
        parts = text.split("\n\n", 1)
        if len(parts) == 2:
            text = parts[0] + "\n\n" + m1_block
        else:
            text = text + "\n\n" + m1_block

    # dedupe deliverable spam in M1
    text = re.sub(
        r"(Keep the deliverable as a Go CLI:.*?)\n\n(?=Keep the deliverable)",
        r"\1\n\n",
        text,
    )
    text = re.sub(
        r"Keep the deliverable as a Go CLI: the verifier compiles `/app/cmd/reconcile/main\.go` with the Go toolchain available at `/usr/local/go/bin/go` and then runs the produced binary\.\s*",
        "",
        text,
    )

    new = text.strip() + "\n"
    if new != path.read_text(encoding="utf-8"):
        write_lf(path, new)
        return True
    return False


def fix_m3_instruction(path: Path, spec: dict) -> bool:
    if not path.is_file():
        return False
    text = path.read_text(encoding="utf-8")
    col = spec["category_col"]
    cats = cats_text(spec["cats"])
    alias_line = ", ".join(f"`{a}` means `{c}`" for a, c in spec["aliases"])
    alias_title = col.replace("_", " ").title().replace(" ", "_")

    text = text.replace("Inspection source row can be consumed once.", "Each source row can be consumed once.")
    text = text.replace("Inspection source row", "Each source row")
    text = re.sub(r"Access_Tier", col, text)
    text = re.sub(r"Hold_Type", col, text)
    text = re.sub(r"Rate_Type", col, text)
    text = re.sub(r"Temp_Band", col, text)
    text = re.sub(r"Cargo_Class", col, text)
    text = re.sub(r"Care_Level", col, text)
    text = re.sub(r"Care_Room", col, text)
    text = re.sub(
        rf"{re.escape(alias_title)} aliases",
        f"`{col}` aliases",
        text,
    )
    text = re.sub(
        rf"canonical match-eligible {col} values remain exactly",
        f"canonical match-eligible `{col}` values remain exactly",
        text,
    )
    text = re.sub(
        rf"same unknown Hold_Type",
        f"same unknown `{col}`",
        text,
    )
    text = re.sub(
        rf"same unknown Rate_Type",
        f"same unknown `{col}`",
        text,
    )
    text = re.sub(
        rf"post-normalization canonical Hold_Type gate for",
        f"post-normalization canonical `{col}` gate for",
        text,
    )
    text = re.sub(
        rf"post-normalization canonical Rate_Type gate for",
        f"post-normalization canonical `{col}` gate for",
        text,
    )

    tie = (
        f"When duplicate `{spec['source_id_col']}` values share the same latest `{spec['source_ts_col']}`, "
        f"the earliest source input row wins the tie-break."
    )
    if tie not in text:
        text = text.replace(
            "multiple unused candidates are resolved by latest source timestamp with earliest input row as the tie-breaker.",
            "multiple unused candidates are resolved by latest source timestamp with earliest input row as the tie-breaker. "
            + tie,
        )

    if f"`{col}` aliases must be normalized" not in text and alias_line:
        text = text.replace(
            f"and the {col} matches after alias normalization.",
            f"and the `{col}` matches after alias normalization. `{col}` aliases must be normalized before matching: {alias_line}.",
        )

    new = text.strip() + "\n"
    if new != path.read_text(encoding="utf-8"):
        write_lf(path, new)
        return True
    return False


def fix_support_matrix(path: Path) -> bool:
    if not path.is_file():
        return False
    text = path.read_text(encoding="utf-8")
    new = text.replace("CUV", "CSV").replace("cuv", "csv")
    if new != text:
        write_lf(path, new)
        return True
    return False


def inject_test(path: Path, snippet: str, marker: str) -> bool:
    if not path.is_file():
        return False
    text = path.read_text(encoding="utf-8")
    if marker in text:
        return False
    write_lf(path, text.rstrip() + "\n" + snippet)
    return True


def fix_m3_test_docstring(path: Path) -> bool:
    if not path.is_file():
        return False
    text = path.read_text(encoding="utf-8")
    old = '"""Window eligibility, malformed times, latest candidate selection, order, and blank unmatched access_tier should hold."""'
    new = (
        '"""Closed windows, malformed timestamps, latest hold_ts selection among duplicate hold_id rows, '
        'earliest-input tie-break on equal hold_ts, and blank unmatched category fields should hold."""'
    )
    if old not in text:
        old2 = '"""Window eligibility, malformed times, latest candidate selection, order, and blank unmatched'
        if old2 in text:
            text = re.sub(
                r'"""Window eligibility, malformed times, latest candidate selection, order, and blank unmatched[^"]*"""',
                new,
                text,
                count=1,
            )
            write_lf(path, text)
            return True
        return False
    write_lf(path, text.replace(old, new))
    return True


def fix_hold_release_task(spec: dict, lang: str) -> None:
    task = ROOT / spec["slug"]
    changes = []
    if fix_m1_instruction(task / "steps/milestone_1/instruction.md", spec, lang):
        changes.append("m1 instruction")
    if fix_m3_instruction(task / "steps/milestone_3/instruction.md", spec):
        changes.append("m3 instruction")
    for sub in ("environment/docs", "docs"):
        if fix_support_matrix(task / sub / "support_matrix.md"):
            changes.append("support_matrix")

    m1_test = task / "steps/milestone_1/tests/test_m1.py"
    snippet = M1_NON_NUMERIC_TEST.format(
        source_ts_col=spec["source_ts_col"],
        action_ts_col=spec["action_ts_col"],
        cat0=spec["cats_m1"][0],
        posted=spec["posted_status"],
        reason0=spec["reasons"][0],
        category_col=spec["category_col"],
    )
    if inject_test(m1_test, snippet, "test_non_numeric_timestamps_stay_unmatched"):
        changes.append("m1 non-numeric test")

    m3_test = task / "steps/milestone_3/tests/test_m3.py"
    alias2 = spec["aliases"][2][0]
    snippet3 = M3_NON_NUMERIC_TEST.format(
        action_ts_col=spec["action_ts_col"],
        cat2=spec["cats"][2],
        alias2=alias2,
        posted=spec["posted_status"],
        reason0=spec["reasons"][0],
        category_col=spec["category_col"],
    )
    if inject_test(m3_test, snippet3, "test_non_numeric_release_timestamp_stays_unmatched"):
        changes.append("m3 non-numeric test")
    if fix_m3_test_docstring(m3_test):
        changes.append("m3 docstring")

    print(f"{spec['slug']}: {', '.join(changes) if changes else 'no changes'}")


def fix_matcher_m1_instruction(path: Path) -> bool:
    if not path.is_file():
        return False
    text = path.read_text(encoding="utf-8")
    orig = text
    # Ensure status values explicitly stated
    if "The report `status` column must use only the exact strings `MATCHED` and `UNMATCHED`." not in text:
        text = text.rstrip() + "\n\nThe report `status` column must use only the exact strings `MATCHED` and `UNMATCHED`.\n"
    # Non-numeric amounts note if amounts mentioned
    if "amount" in text.lower() and "Non-numeric amount" not in text:
        text = text.replace(
            "Report fields should not carry incidental surrounding spaces from the input.",
            "Report fields should not carry incidental surrounding spaces from the input. "
            "Non-numeric amount fields make the row ineligible for matching.",
        )
    if text != orig:
        write_lf(path, text)
        return True
    return False


MATCHER_ALIAS_SPECS = [
    {
        "slug": "go-escape-room-booking-refund-matcher",
        "tier_col": "room_tier",
        "aliases": [("EA", "EASY"), ("HD", "HARD"), ("VP", "VIP")],
        "rename_tests": [("test_dy_alias_", "test_ea_alias_"), ("test_an_alias_", "test_vp_alias_")],
    },
    {
        "slug": "go-food-truck-rally-voucher-matcher",
        "tier_col": "meal_tier",
        "aliases": [("SN", "SNACK"), ("ML", "MEAL"), ("CB", "COMBO")],
        "rename_tests": [],
    },
    {
        "slug": "go-helicopter-tour-deposit-reconciler",
        "tier_col": "cabin_tier",
        "aliases": [("ST", "STD"), ("PM", "PREM"), ("LX", "LUX")],
        "rename_tests": [],
    },
    {
        "slug": "go-ice-rink-session-credit-matcher",
        "tier_col": "rink_pass",
        "aliases": [("PR", "PRAC"), ("GM", "GAME"), ("LG", "LEAG")],
        "rename_tests": [],
    },
    {
        "slug": "go-photo-booth-print-credit-matcher",
        "tier_col": "pack_tier",
        "aliases": [("MI", "MINI"), ("SD", "STANDARD"), ("MX", "MAX")],
        "rename_tests": [],
    },
    {
        "slug": "go-solar-install-rebate-matcher",
        "tier_col": "system_tier",
        "aliases": [("HO", "HOME"), ("BZ", "BIZ"), ("IN", "IND")],
        "rename_tests": [],
    },
    {
        "slug": "go-winery-tasting-refund-matcher",
        "tier_col": "flight_tier",
        "aliases": [("RD", "RED"), ("WH", "WHITE"), ("MX", "MIXED")],
        "rename_tests": [],
    },
]


def alias_instruction_text(tier_col: str, aliases: list[tuple[str, str]]) -> str:
    a, b, c = aliases
    codes = f"`{a[0]}`, `{b[0]}`, `{c[0]}`"
    canonical = f"`{a[1]}`, `{b[1]}`, `{c[1]}`"
    means = ", ".join(f"`{x}` means `{y}`" for x, y in aliases)
    return (
        f"legacy credit {tier_col} aliases {codes} should be treated as canonical {canonical}. "
        f"Alias normalization: {means}."
    )


def fix_matcher_aliases(spec: dict) -> None:
    slug = spec["slug"]
    task = ROOT / slug
    tier_col = spec["tier_col"]
    aliases = spec["aliases"]
    replacement = alias_instruction_text(tier_col, aliases)
    old_pat = re.compile(
        rf"legacy credit {re.escape(tier_col)} aliases `DY`, `MO`, `AN` should be treated as canonical `[^`]+`, `[^`]+`, and `[^`]+`\."
    )
    m3_old = re.compile(
        rf"Legacy aliases from milestone 2 still apply \(`DY` means `[^`]+`, `MO` means `[^`]+`, `AN` means `[^`]+`\)"
    )
    m3_new = "Legacy aliases from milestone 2 still apply (" + ", ".join(f"`{a}` means `{c}`" for a, c in aliases) + ")"

    for path in (task / "steps/milestone_2/instruction.md", task / "steps/milestone_1/instruction.md"):
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        text = old_pat.sub(replacement, text)
        if "Non-numeric amount fields" not in text and "amount" in text:
            text = text.replace(
                "The report `status` column must use only the exact strings `MATCHED` and `UNMATCHED`.",
                "Non-numeric amount fields make the row ineligible for matching; the program must continue processing remaining rows.\n\n"
                "The report `status` column must use only the exact strings `MATCHED` and `UNMATCHED`.",
            )
        write_lf(path, text)

    m3 = task / "steps/milestone_3/instruction.md"
    if m3.is_file():
        text = m3.read_text(encoding="utf-8")
        text = m3_old.sub(m3_new, text)
        write_lf(m3, text)

    sm = task / "environment/docs/support_matrix.md"
    if sm.is_file():
        a, b, c = aliases
        write_lf(
            sm,
            f"# Support matrix\n\nAllowed {tier_col} values are {a[1]}, {b[1]}, {c[1]}. "
            f"Legacy aliases are {a[0]} -> {a[1]}, {b[0]} -> {b[1]}, {c[0]} -> {c[1]}.\n",
        )

    for m3_test in (task / "steps/milestone_3/tests/test_m3.py",):
        if not m3_test.is_file():
            continue
        text = m3_test.read_text(encoding="utf-8")
        for old, new in spec.get("rename_tests", []):
            text = text.replace(old, new)
        text = text.replace("A AN credit", f"A {aliases[2][0]} credit")
        text = text.replace("The EA alias", f"The {aliases[0][0]} alias")
        write_lf(m3_test, text)

    main_go = task / "environment/cmd/reconcile/main.go"
    if main_go.is_file():
        text = main_go.read_text(encoding="utf-8")
        if "loadTripes" in text:
            text = text.replace("loadTripes", "loadBookings")
            write_lf(main_go, text)


def fix_matcher_task(slug: str) -> None:
    changes = []
    if fix_matcher_m1_instruction(ROOT / slug / "steps/milestone_1/instruction.md"):
        changes.append("m1 instruction")
    if fix_support_matrix(ROOT / slug / "environment/docs/support_matrix.md"):
        changes.append("support_matrix")
    print(f"{slug}: {', '.join(changes) if changes else 'no changes'}")


def main() -> int:
    tasks = set(load_tasks())
    for spec in GO_SPECS:
        if spec["slug"] in tasks:
            fix_hold_release_task(spec, "go")
    for spec in RUBY_SPECS:
        if spec["slug"] in tasks:
            fix_hold_release_task(spec, "ruby")

    matchers = sorted(t for t in tasks if t not in {s["slug"] for s in GO_SPECS + RUBY_SPECS})
    for spec in MATCHER_ALIAS_SPECS:
        if spec["slug"] in tasks:
            fix_matcher_aliases(spec)
            print(f"fixed matcher aliases: {spec['slug']}")
    for slug in matchers:
        if slug not in {s["slug"] for s in MATCHER_ALIAS_SPECS}:
            fix_matcher_task(slug)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
