#!/usr/bin/env python3
"""Trim task.toml tags to max 6; drop redundant data-processing."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAX_TAGS = 6
DROP = {"data-processing", "data_processing"}

ALIASES = {
    "ruby-music-royalty-live-settlement-ledger": "ruby-music-royalty-live-settlement-router",
    "ruby-parking-garage-session-refund-matcher": "ruby-parking-garage-session-adjustment-clearing",
    "go-live-auction-bid-reversal-matcher": "go-live-auction-bid-reversal-ledger",
    "pl1-cobol-atm-risk-release-reconciler": "pl1-cobol-atm-risk-release-router",
    "ruby-cooking-class-voucher-refund-matcher": "ruby-cooking-class-voucher-matcher",
    "ruby-go-bash-vineyard-club-credit-ledger": "ruby-go-bash-vineyard-club-shipment-credit-router",
    "cobol-escrow-return-reconciler": "cobol-escrow-return-reconciliation",
}


def folders() -> list[str]:
    out = []
    for line in (ROOT / "needs_revision_mapped.txt").read_text().splitlines():
        if line.strip() and not line.startswith("#"):
            _, plat = line.split(None, 1)
            out.append(ALIASES.get(plat, plat))
    return out


def trim_tags(task_dir: Path) -> bool:
    toml = task_dir / "task.toml"
    if not toml.is_file():
        return False
    text = toml.read_text(encoding="utf-8")
    m = re.search(r'^tags = \[(.*?)\]', text, re.MULTILINE)
    if not m:
        return False
    tags = [t.strip().strip('"').strip("'") for t in m.group(1).split(",") if t.strip()]
    new_tags = [t for t in tags if t not in DROP]
    if len(new_tags) > MAX_TAGS:
        new_tags = new_tags[:MAX_TAGS]
    if new_tags == tags:
        return False
    quoted = ", ".join(f'"{t}"' for t in new_tags)
    new = text[: m.start(1)] + quoted + text[m.end(1) :]
    toml.write_text(new, encoding="utf-8")
    return True


def main() -> None:
    n = 0
    for folder in folders():
        if trim_tags(ROOT / folder):
            print(f"trimmed tags: {folder}")
            n += 1
    print(f"updated {n} tasks")


if __name__ == "__main__":
    main()
