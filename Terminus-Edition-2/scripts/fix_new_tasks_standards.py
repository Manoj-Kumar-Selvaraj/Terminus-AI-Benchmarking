#!/usr/bin/env python3
"""Apply template-standard fixes to all tasks in new_tasks.txt."""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LIST = ROOT / "new_tasks.txt"

sys.path.insert(0, str(ROOT / "scripts"))
from audit_fix_task_toml_timeouts import fix_task_toml  # noqa: E402
from fix_new_task_oracles import COBOL_TASKS, GO_SPECS, RUBY_SPECS  # noqa: E402

TEST_SH = """#!/bin/bash
set -uo pipefail
mkdir -p /logs/verifier
echo 0 > /logs/verifier/reward.txt

python3 -m pytest --ctrf /logs/verifier/ctrf.json /tests/{test_file} -rA

if [ $? -eq 0 ]; then
    echo 1 > /logs/verifier/reward.txt
else
    echo 0 > /logs/verifier/reward.txt
fi
"""

COBOL_TEMPLATE_DATA = ("dock_fees.dat", "reversals.dat")
COBOL_TEMPLATE_CONFIG = ("harbor_calendar.txt",)
RUBY_TEMPLATE_DATA = ("sessions.csv", "adjustments.csv")


def load_tasks() -> list[str]:
    return [
        line.strip()
        for line in LIST.read_text(encoding="utf-8-sig").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]


def write_lf(path: Path, content: str) -> None:
    path.write_text(content.replace("\r\n", "\n"), encoding="utf-8", newline="\n")


def fix_test_sh(task_dir: Path) -> None:
    for milestone in (1, 2, 3):
        path = task_dir / f"steps/milestone_{milestone}/tests/test.sh"
        if path.is_file():
            write_lf(path, TEST_SH.format(test_file=f"test_m{milestone}.py"))


def fix_task_toml_file(task_dir: Path) -> None:
    toml = task_dir / "task.toml"
    if toml.is_file():
        fix_task_toml(toml)


def cleanup_cobol_data(task_dir: Path) -> None:
    for sub in ("data", "samples", "config"):
        base = task_dir / "environment" / sub
        if not base.is_dir():
            continue
        for name in COBOL_TEMPLATE_DATA if sub != "config" else COBOL_TEMPLATE_CONFIG:
            p = base / name
            if p.is_file():
                p.unlink()


def cleanup_ruby_data(task_dir: Path, spec: dict) -> None:
    data = task_dir / "environment" / "data"
    if not data.is_dir():
        return
    have_domain = (data / spec["source_file"]).is_file() and (data / spec["action_file"]).is_file()
    if have_domain:
        for name in RUBY_TEMPLATE_DATA:
            p = data / name
            if p.is_file():
                p.unlink()


def alias_text(spec: dict) -> str:
    return ", ".join(f"`{a}` means `{c}`" for a, c in spec["aliases"])


def cats_text(cats: list[str]) -> str:
    return ", ".join(f"`{c}`" for c in dict.fromkeys(cats))


def hold_rubric(spec: dict, lang: str) -> str:
    col = spec["category_col"]
    impl = "/app/cmd/reconcile/main.go" if lang == "go" else "/app/app/reconcile.rb"
    m1_cats = cats_text(spec["cats_m1"])
    all_cats = cats_text(list(dict.fromkeys(spec["cats"])))
    aliases = alias_text(spec)
    report = spec["report_file"]
    summary = spec["summary_file"]
    posted = spec["posted_status"]
    scope = spec["window_scope_col"]
    return f"""# Rubric 1

Agent investigates `{impl}`, `/app/data/{spec["source_file"]}`, and `/app/data/{spec["action_file"]}` instead of unrelated files, +2
Agent satisfies milestone 1 core requirement: full source identifier and identity fields match, integer amount match, `{posted}` source status, allowed correction reasons, and numeric timestamps where `{spec["action_ts_col"]}` is on or after `{spec["source_ts_col"]}`, +5
Agent restricts milestone 1 match-eligible `{col}` values to {m1_cats} only and leaves unknown values unmatched, +3
Agent consumes each source row at most once while preserving correction input order, +3
Agent writes `/app/out/{report}` and `/app/out/{summary}` with required schema, `MATCHED`/`UNMATCHED` only, blank unmatched `{col}`, and positive summary totals, +3
Agent hardcodes final output files instead of fixing reconciliation logic, -5
Agent tampers with verifier harness files, oracle scripts, or input fixtures to force a pass, -5

# Rubric 2

Agent normalizes legacy `{col}` aliases ({aliases}) on both source and correction rows after trim and case folding, +5
Agent expands milestone 2 canonical match-eligible `{col}` values to {all_cats}, +3
Agent emits canonical `{col}` values in matched report rows rather than raw alias codes, +3
Agent preserves milestone 1 full-id, identity, consumption, schema, and positive-total behavior while adding aliases, +3
Agent leaves `{col}` blank on unmatched rows after alias-aware matching, +3
Agent applies `/app/config/windows.csv` filtering in milestone 2 before window rules belong in scope, -3
Agent regresses milestone 1 behavior while implementing alias normalization, -3

# Rubric 3

Agent applies open window gates from `/app/config/windows.csv` while preserving all earlier matching rules, +5
Agent requires source `{spec["source_ts_col"]}` inside an `OPEN` window for the same `{scope}` and rejects closed, missing, malformed, or unlisted windows, +5
Agent rejects releases whose `{spec["action_ts_col"]}` is before `{spec["source_ts_col"]}` or after the window close, +3
Agent chooses the eligible source with the latest `{spec["source_ts_col"]}` when multiple unused rows qualify for one correction, +5
Agent breaks tied timestamps by selecting the earliest source input row and tracks consumption by row position, +3
Agent preserves alias normalization and canonical report output under window-gated matching, +3
Agent validates final CSV and summary artifacts before finishing milestone 3, +2
Agent treats closed or unlisted windows as eligible open windows, -5
Agent regresses milestone 1 or 2 matching behavior while adding window or tie-break logic, -3
"""


def fix_airport_instruction(task_dir: Path) -> None:
    for path in task_dir.glob("steps/milestone_*/instruction.md"):
        text = path.read_text(encoding="utf-8")
        text = text.replace(
            "the `check_type` field is one of the canonical values `MEDICAL`, `CUSTOMS`, or `MEDICAL` after alias normalization",
            "the `check_type` field is one of the canonical values `MEDICAL` or `CUSTOMS`",
        )
        text = text.replace(
            "the canonical match-eligible check_type values are exactly `MEDICAL`, `CUSTOMS`, or `MEDICAL`",
            "the canonical match-eligible check_type values are exactly `MEDICAL`, `CUSTOMS`, and `MEDICAL` via the `SE` alias",
        )
        text = text.replace(
            "`SC` means `SECURITY`, `CU` means `CUSTOMS`, `MD` means `MEDICAL`",
            "`IN` means `MEDICAL`, `CU` means `CUSTOMS`, `SE` means `MEDICAL`",
        )
        if "milestone_1" in path.parts:
            text = re.sub(
                r"using `/app/config/windows\.csv` for the active realtime window rules\. ",
                "",
                text,
            )
        write_lf(path, text)


def main() -> None:
    tasks = load_tasks()
    go_slugs = {s["slug"] for s in GO_SPECS}
    ruby_by_slug = {s["slug"]: s for s in RUBY_SPECS}

    for name in tasks:
        task_dir = ROOT / name
        if not task_dir.is_dir():
            print(f"skip missing {name}")
            continue
        fix_test_sh(task_dir)
        if name in go_slugs or name in ruby_by_slug:
            fix_task_toml_file(task_dir)
        print(f"fixed test.sh + task.toml checks: {name}")

    for task in COBOL_TASKS:
        cleanup_cobol_data(ROOT / task["slug"])
        print(f"cleaned COBOL template data: {task['slug']}")

    for spec in RUBY_SPECS:
        cleanup_ruby_data(ROOT / spec["slug"], spec)
        write_lf(ROOT / spec["slug"] / "rubric.txt", hold_rubric(spec, "ruby"))
        print(f"fixed ruby standards: {spec['slug']}")

    for spec in GO_SPECS:
        write_lf(ROOT / spec["slug"] / "rubric.txt", hold_rubric(spec, "go"))
        print(f"fixed go hold-release standards: {spec['slug']}")

    fix_airport_instruction(ROOT / "go-airport-gate-baggage-hold-release")
    print("fixed airport instructions")

    # Fix test.sh for matcher tasks too (already done in loop)
    print(f"Done. Updated {len(tasks)} tasks.")


if __name__ == "__main__":
    main()
