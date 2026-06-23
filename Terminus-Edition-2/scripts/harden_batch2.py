#!/usr/bin/env python3
"""Harden LLMaJ batch 2 tasks (5 credit matchers)."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from scaffold_fresh_batch_20260602 import FRESH_TASKS, harden_task  # noqa: E402
from scaffold_go_tasks_from_bike import TASKS  # noqa: E402
from harden_llmaj_batch_5_20260602 import (  # noqa: E402
    enrich_m1_instruction,
    enrich_m3_instruction_dates,
    add_m3_schema_test,
    harden_credit_matcher,
    fix_test_docstrings,
)
from llmaj_harden_go_matcher import (  # noqa: E402
    add_m1_unmatched_trim_test,
    fix_m3_tests_names_and_docs,
    fix_operations_doc,
    fix_support_matrix_title,
)

BATCH2 = [
    "go-community-pool-lap-credit-matcher",
    "go-ice-rink-session-credit-matcher",
    "go-laundromat-cycle-rebate-matcher",
    "go-mini-golf-scorecard-credit-matcher",
    "go-museum-visit-audio-credit-matcher",
]

LOAD_TYPOS = {
    "go-ice-rink-session-credit-matcher": ("loadSessiones", "loadSessions"),
}


def spec_for(slug: str) -> dict:
    for s in FRESH_TASKS:
        if s["slug"] == slug:
            return dict(s)
    for s in TASKS:
        if s["slug"] == slug:
            out = dict(s)
            if slug in LOAD_TYPOS:
                out["load_typo"], out["load_fix"] = LOAD_TYPOS[slug]
            return out
    raise KeyError(slug)


def fix_domain_trim_tests(dest: Path, spec: dict) -> None:
    """Fix escape-room tier names left in trim tests."""
    c0, c1, c2 = spec["cats"]
    pairs = [
        ("easy", c0.lower()),
        ("EASY", c0),
        ("hard", c1.lower()),
        ("HARD", c1),
        ("vip", c2.lower()),
        ("VIP", c2),
        ("MEAL", c1),
        (",hd", f",{spec['aliases'][1][0].lower()}"),
    ]
    for test_py in dest.glob("steps/milestone_*/tests/test_m*.py"):
        text = test_py.read_text(encoding="utf-8")
        for old, new in pairs:
            text = text.replace(old, new)
        # second trim line: voucher/refund action tier must match order tier
        if "7200, MEAL" in text or f"7200, {c2}" in text and c1 != c2:
            text = text.replace(f"7200, {c2} ", f"7200, {c1} ")
        if f'["{c0}", "{c2}"]' in text:
            text = text.replace(f'["{c0}", "{c2}"]', f'["{c0}", "{c1}"]')
        test_py.write_text(text, encoding="utf-8")


def harden_one(slug: str) -> None:
    spec = spec_for(slug)
    dest = ROOT / slug
    # Do not call restore_tests_from_escape_room again (EA->PR breaks LEAG-tier names).
    from scaffold_fresh_batch_20260602 import (
        harden_main_go,
        harden_solve1,
        harden_solve3,
        harden_m3_instruction,
        patch_shipped_data_csv,
        fix_instructions,
        fix_alias_legacy_test,
        fix_m3_test_names,
        harden_test_sh,
    )

    harden_main_go(dest / "environment/cmd/reconcile/main.go", spec)
    harden_solve1(dest / "steps/milestone_1/solution/solve1.sh", spec)
    harden_solve3(dest / "steps/milestone_3/solution/solve3.sh", spec)
    harden_m3_instruction(dest / "steps/milestone_3/instruction.md", spec)
    patch_shipped_data_csv(dest, spec)
    fix_instructions(dest, spec)
    fix_alias_legacy_test(dest, spec)
    fix_m3_test_names(dest, spec)
    for test_sh in dest.glob("steps/milestone_*/tests/test.sh"):
        harden_test_sh(test_sh)
    enrich_m1_instruction(dest / "steps/milestone_1/instruction.md", spec)
    enrich_m3_instruction_dates(dest / "steps/milestone_3/instruction.md", spec)
    fix_test_docstrings(dest, spec)
    fix_m3_tests_names_and_docs(dest, spec)
    fix_operations_doc(dest, spec)
    fix_support_matrix_title(dest, spec)
    add_m1_unmatched_trim_test(dest, spec)
    add_m3_schema_test(dest / "steps/milestone_3/tests/test_m3.py", spec)
    if slug != "go-ice-rink-session-credit-matcher":
        fix_domain_trim_tests(dest, spec)
    for milestone in (2, 3):
        p = dest / f"steps/milestone_{milestone}/tests/test_m{milestone}.py"
        if p.is_file():
            t = p.read_text(encoding="utf-8")
            t = t.replace("ESCS =", "SOURCE_FILE =").replace("ESCS.write_text", "SOURCE_FILE.write_text")
            p.write_text(t, encoding="utf-8")
    # ensure solve3 is food-truck style (not broken SlotDate patch)
    from scaffold_fresh_batch_20260602 import harden_solve3

    harden_solve3(dest / "steps/milestone_3/solution/solve3.sh", spec)


def main() -> None:
    for slug in BATCH2:
        harden_one(slug)
        print(f"hardened {slug}")


if __name__ == "__main__":
    main()
