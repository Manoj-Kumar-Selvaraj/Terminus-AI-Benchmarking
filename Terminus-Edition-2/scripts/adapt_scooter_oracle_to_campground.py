#!/usr/bin/env python3
"""Adapt cobol-scooter oracle COBOL sources to cobol-campground naming and domain rules."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCOOTER = ROOT / "cobol-scooter-ride-surcharge-reversal" / "steps"
CAMP = ROOT / "cobol-campground-site-deposit-matcher" / "steps"

REPLACEMENTS = [
    ("scooter-surcharge-reconcile", "camp-deposit-reconcile"),
    ("/app/data/ride_charges.dat", "/app/data/site_fees.dat"),
    ("/app/data/surcharge_reversals.dat", "/app/data/deposit_returns.dat"),
    ("/app/out/scooter_surcharge_report.csv", "/app/out/camp_deposit_report.csv"),
    ("/app/out/scooter_surcharge_summary.txt", "/app/out/camp_deposit_summary.txt"),
    ("record_id,account,zone_code,amount_cents,reason,status", "record_id,account,site_class,amount_cents,reason,status"),
    ("/app/config/fleet_calendar.txt", "/app/config/season_calendar.txt"),
    ("/app/config/categories.csv", "/app/config/categories.csv"),  # same path, different semantics later
    ('"S02"', '"C02"'),
    ('"S07"', '"C06"'),
    ('"S15"', '"C10"'),
    ("S02", "C02"),
    ("S07", "C06"),
    ("S15", "C10"),
    ('SRC-STATUS(I) = "Z"', 'SRC-STATUS(I) = "G"'),
    ('"CBD"', '"TNT"'),
    ('"RES"', '"RV"'),
    ('"UNI"', '"CBN"'),
    ("CBD", "TNT"),
    ("RES", "RV"),
    ("UNI", "CBN"),
    ("zone_code", "site_class"),
    ("ZONE", "SITE"),
    ("zone", "site"),
    ("NORMALIZE-ZONE", "NORMALIZE-SITE"),
    ("CANON-ZONE", "CANON-SITE"),
    ("ACT-ZONE", "ACT-SITE"),
    ("SRC-ZONE", "SRC-SITE"),
    # Scooter alias keys -> campground alias keys (first two chars)
    ('"CB"', '"CB"'),  # CB->CBN vs CB->CBD - handled in alias logic below
    ('"RE"', '"R0"'),
    ('"UN"', '"NT"'),
    ("ALIAS-KEY", "ALIAS-KEY"),  # noop anchor
]

# Scooter M2 aliases: CB->CBD, RE->RES, UN->UNI  => Camp: CB->CBN, R0->RV, NT->TNT
ALIAS_BLOCK_SCOOTER = '''           IF ALIAS-KEY = "CB"
               MOVE "CBD" TO CANON-CAT
           ELSE IF ALIAS-KEY = "RE"
               MOVE "RES" TO CANON-CAT
           ELSE IF ALIAS-KEY = "UN"
               MOVE "UNI" TO CANON-CAT'''

ALIAS_BLOCK_CAMP = '''           IF ALIAS-KEY = "CB"
               MOVE "CBN" TO CANON-CAT
           ELSE IF ALIAS-KEY = "R0"
               MOVE "RV" TO CANON-CAT
           ELSE IF ALIAS-KEY = "NT"
               MOVE "TNT" TO CANON-CAT'''

SURCHARGE_TO_DEPOSIT = [
    ("max_reversal_cents", "max_deposit_cents"),
    ("surcharge_enabled", "enabled"),
    ("SURCHARGE", "DEPOSIT"),
    ("REVERSAL", "DEPOSIT"),
    ("scooter", "camp"),
    ("Scooter", "Camp"),
]

SOLVE_SH = '''#!/bin/bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${{BASH_SOURCE[0]}}")" && pwd)"
MILESTONE="{milestone}"
if grep -q 'CALL "SYSTEM" USING "python3' /app/src/camp_deposit_reconcile.cbl 2>/dev/null; then
  :
else
  if [[ "$MILESTONE" != "1" ]] && ! grep -q 'NORMALIZE-SITE' /app/src/camp_deposit_reconcile.cbl 2>/dev/null; then
    bash "/steps/milestone_{prev}/solution/solve{prev}.sh"
  fi
fi
cp "$SCRIPT_DIR/oracle_m{milestone}.cbl" /app/src/camp_deposit_reconcile.cbl
/app/scripts/run_batch.sh
'''


def adapt_text(text: str) -> str:
    for old, new in REPLACEMENTS:
        text = text.replace(old, new)
    text = text.replace(ALIAS_BLOCK_SCOOTER, ALIAS_BLOCK_CAMP)
    for old, new in SURCHARGE_TO_DEPOSIT:
        text = text.replace(old, new)
    # M5 branch policies file path
    text = text.replace("/app/config/branch_policies.csv", "/app/config/branch_policies.csv")
    return text


def write_solve(milestone: int) -> None:
    prev = milestone - 1 if milestone > 1 else 1
    content = SOLVE_SH.format(milestone=milestone, prev=prev)
    path = CAMP / f"milestone_{milestone}" / "solution" / f"solve{milestone}.sh"
    path.write_text(content, encoding="utf-8", newline="\n")
    path.chmod(0o755)


def main() -> None:
    for m in range(1, 6):
        src = SCOOTER / f"milestone_{m}" / "solution" / f"oracle_m{m}.cbl"
        dst = CAMP / f"milestone_{m}" / "solution" / f"oracle_m{m}.cbl"
        if not src.is_file():
            raise SystemExit(f"Missing {src}")
        text = adapt_text(src.read_text(encoding="utf-8"))
        dst.write_text(text, encoding="utf-8", newline="\n")
        write_solve(m)
        print(f"Wrote {dst.name} and solve{m}.sh")


if __name__ == "__main__":
    main()
