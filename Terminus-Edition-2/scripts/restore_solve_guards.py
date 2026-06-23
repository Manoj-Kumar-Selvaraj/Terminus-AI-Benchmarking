#!/usr/bin/env python3
"""Restore bash lines removed from guarded if-blocks in solve scripts."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Full file restores from known-good copies
RESTORE_FILES = {
    "cobol-hospital-claim-denial-reconciler/steps/milestone_2/solution/solve2.sh": ROOT
    / "Revision-ChatGpt/Backups/cobol-hospital-claim-denial-reconciler_backup_20260607_205100/steps/milestone_2/solution/solve2.sh",
    "cobol-hospital-claim-denial-reconciler/steps/milestone_3/solution/solve3.sh": ROOT
    / "Revision-ChatGpt/Backups/cobol-hospital-claim-denial-reconciler_backup_20260607_205100/steps/milestone_3/solution/solve3.sh",
    "cobol-utility-meter-adjustment-clearing/steps/milestone_2/solution/solve2.sh": ROOT
    / "cobol-utility-meter-adjustment-clearing_20260608_184830/steps/milestone_2/solution/solve2.sh",
    "cobol-utility-meter-adjustment-clearing/steps/milestone_3/solution/solve3.sh": ROOT
    / "cobol-utility-meter-adjustment-clearing_20260608_184830/steps/milestone_3/solution/solve3.sh",
    "go-clinic-visit-credit-matcher/steps/milestone_2/solution/solve2.sh": ROOT
    / "Revision-ChatGpt/Backups/go-clinic-visit-credit-matcher_backup_20260606_224153/steps/milestone_2/solution/solve2.sh",
    "go-clinic-visit-credit-matcher/steps/milestone_3/solution/solve3.sh": ROOT
    / "Revision-ChatGpt/Backups/go-clinic-visit-credit-matcher_backup_20260606_224153/steps/milestone_3/solution/solve3.sh",
    "go-clinic-visit-credit-matcher/steps/milestone_4/solution/solve4.sh": ROOT
    / "Revision-ChatGpt/Backups/go-clinic-visit-credit-matcher_backup_20260606_224153/steps/milestone_4/solution/solve4.sh",
    "go-parking-citation-credit-matcher/steps/milestone_2/solution/solve2.sh": ROOT
    / "go-parking-citation-credit-matcher_20260604_difficulty_revision_linux/steps/milestone_2/solution/solve2.sh",
    "go-parking-citation-credit-matcher/steps/milestone_3/solution/solve3.sh": ROOT
    / "go-parking-citation-credit-matcher_20260604_difficulty_revision_linux/steps/milestone_3/solution/solve3.sh",
}

# Inline guard restores: (relative path, grep needle fragment, bash line)
GUARD_LINES = [
    (
        "cobol-bowling-league-fee-reversal/steps/milestone_2/solution/solve2.sh",
        "SRC-USED(I) NOT = \"Y\"",
        "  bash /steps/milestone_1/solution/solve1.sh",
    ),
    (
        "cobol-bowling-league-fee-reversal/steps/milestone_3/solution/solve3.sh",
        "SRC-USED(I) NOT = \"Y\"",
        "  bash /steps/milestone_1/solution/solve1.sh",
    ),
    (
        "cobol-bowling-league-fee-reversal/steps/milestone_3/solution/solve3.sh",
        'IF ACT-CAT(1:2) = "ST"',
        "  bash /steps/milestone_2/solution/solve2.sh",
    ),
    (
        "cobol-pension-contribution-reversal/steps/milestone_2/solution/solve2.sh",
        "SRC-USED(I) NOT = \"Y\"",
        "  bash /steps/milestone_1/solution/solve1.sh",
    ),
    (
        "cobol-pension-contribution-reversal/steps/milestone_3/solution/solve3.sh",
        "SRC-USED(I) NOT = \"Y\"",
        "  bash /steps/milestone_1/solution/solve1.sh",
    ),
    (
        "cobol-pension-contribution-reversal/steps/milestone_3/solution/solve3.sh",
        'IF ACT-CAT(1:2) = "EE"',
        "  bash /steps/milestone_2/solution/solve2.sh",
    ),
    (
        "cobol-telehealth-session-credit-clearing/steps/milestone_2/solution/solve2.sh",
        "SRC-USED(I) NOT = \"Y\"",
        "  bash /steps/milestone_1/solution/solve1.sh",
    ),
    (
        "cobol-telehealth-session-credit-clearing/steps/milestone_3/solution/solve3.sh",
        "SRC-USED(I) NOT = \"Y\"",
        "  bash /steps/milestone_1/solution/solve1.sh",
    ),
    (
        "cobol-telehealth-session-credit-clearing/steps/milestone_3/solution/solve3.sh",
        'IF ACT-CAT(1:2) = "GN"',
        "  bash /steps/milestone_2/solution/solve2.sh",
    ),
    (
        "go-conference-sponsor-rebate-matcher/steps/milestone_2/solution/solve2.sh",
        "usedSponsorships",
        '  bash "$SCRIPT_DIR/solve1.sh"',
    ),
    (
        "go-conference-sponsor-rebate-matcher/steps/milestone_3/solution/solve3.sh",
        "canonicalLevel",
        '  bash "$SCRIPT_DIR/solve2.sh"',
    ),
    (
        "cobol-campground-site-deposit-matcher/steps/milestone_2/solution/solve2.sh",
        "NORMALIZE-SITE",
        '    bash "/steps/milestone_1/solution/solve1.sh"',
    ),
    (
        "cobol-campground-site-deposit-matcher/steps/milestone_3/solution/solve3.sh",
        "NORMALIZE-SITE",
        '    bash "/steps/milestone_1/solution/solve1.sh"',
    ),
    (
        "cobol-campground-site-deposit-matcher/steps/milestone_4/solution/solve4.sh",
        "NORMALIZE-SITE",
        '    bash "/steps/milestone_1/solution/solve1.sh"',
    ),
    (
        "cobol-campground-site-deposit-matcher/steps/milestone_5/solution/solve5.sh",
        "NORMALIZE-SITE",
        '    bash "/steps/milestone_1/solution/solve1.sh"',
    ),
]


def restore_guard(path: Path, needle: str, bash_line: str) -> bool:
    text = path.read_text(encoding="utf-8")
    pattern = re.compile(
        rf'(if[^\n]*{re.escape(needle)}[^\n]*\n)\s*\n(\s*fi\b)',
        re.MULTILINE,
    )
    new_text, n = pattern.subn(rf"\1{bash_line}\n\2", text, count=1)
    if n:
        path.write_text(new_text, encoding="utf-8")
    return bool(n)


def remove_empty_if(path: Path) -> bool:
    text = path.read_text(encoding="utf-8")
    new_text = re.sub(
        r'if \[ -f "\$SCRIPT_DIR/solve\d+\.sh" \]; then\s*\n\s*fi\s*\n',
        "",
        text,
    )
    if new_text != text:
        path.write_text(new_text, encoding="utf-8")
        return True
    return False


def main() -> int:
    for rel, src in RESTORE_FILES.items():
        dst = ROOT / rel
        if src.is_file() and dst.is_file():
            dst.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
            print(f"restored {rel}")

    for rel, needle, bash_line in GUARD_LINES:
        path = ROOT / rel
        if path.is_file() and restore_guard(path, needle, bash_line):
            print(f"guard {rel} ({needle[:24]}...)")

    for rel in (
        "cobol-municipal-return-clearing/steps/milestone_2/solution/solve2.sh",
        "cobol-municipal-return-clearing/steps/milestone_3/solution/solve3.sh",
    ):
        path = ROOT / rel
        if path.is_file() and remove_empty_if(path):
            print(f"removed empty if {rel}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
