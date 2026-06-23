#!/usr/bin/env python3
"""Post-fix scaffolded COBOL tasks: status codes in instructions and alias codes in tests."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

FIXES = [
    {
        "slug": "cobol-bowling-league-fee-reversal",
        "status": "L",
        "aliases": (("SP", "ST"), ("DY", "SC"), ("TN", "CO")),
    },
    {
        "slug": "cobol-zoo-admission-refund-clearing",
        "status": "A",
        "aliases": (("SP", "AD"), ("DY", "CH"), ("TN", "SE")),
    },
    {
        "slug": "cobol-campground-site-deposit-matcher",
        "status": "G",
        "aliases": (("SP", "NT"), ("DY", "R0"), ("TN", "CB")),
    },
    {
        "slug": "cobol-laundromat-load-credit-clearing",
        "status": "R",
        "aliases": (("SP", "SM"), ("DY", "MD"), ("TN", "LG")),
    },
    {
        "slug": "cobol-scooter-ride-surcharge-reversal",
        "status": "Z",
        "aliases": (("SP", "CB"), ("DY", "RE"), ("TN", "UN")),
    },
]


def main() -> None:
    for spec in FIXES:
        root = ROOT / spec["slug"]
        if not root.exists():
            continue
        for path in root.rglob("*.md"):
            text = path.read_text(encoding="utf-8")
            text = text.replace("source status `D`", f"source status `{spec['status']}`")
            text = text.replace("status `D`", f"status `{spec['status']}`")
            path.write_text(text, encoding="utf-8")
        for path in list(root.rglob("test_m*.py")) + list(
            (root / "environment").rglob("*.dat")
        ):
            text = path.read_text(encoding="utf-8")
            for old, new in spec["aliases"]:
                text = text.replace(f'"{old}"', f'"{new}"')
                text = text.replace(f", {old},", f", {new},")
            path.write_text(text, encoding="utf-8")
        m1 = root / "steps" / "milestone_1" / "instruction.md"
        text = m1.read_text(encoding="utf-8")
        if "status `" not in text or f"status `{spec['status']}`" not in text:
            text = re.sub(
                r"source status `.\`",
                f"source status `{spec['status']}`",
                text,
                count=1,
            )
            m1.write_text(text, encoding="utf-8")
        print(f"fixed {spec['slug']}")


if __name__ == "__main__":
    main()
