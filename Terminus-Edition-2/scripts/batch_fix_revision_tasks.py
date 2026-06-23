#!/usr/bin/env python3
"""Batch mechanical fixes for NEEDS_REVISION tasks (agent-review hygiene)."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

ALIASES = {
    "ruby-music-royalty-live-settlement-ledger": "ruby-music-royalty-live-settlement-router",
    "ruby-parking-garage-session-refund-matcher": "ruby-parking-garage-session-adjustment-clearing",
    "go-live-auction-bid-reversal-matcher": "go-live-auction-bid-reversal-ledger",
    "pl1-cobol-atm-risk-release-reconciler": "pl1-cobol-atm-risk-release-router",
    "ruby-cooking-class-voucher-refund-matcher": "ruby-cooking-class-voucher-matcher",
    "ruby-go-bash-vineyard-club-credit-ledger": "ruby-go-bash-vineyard-club-shipment-credit-router",
    "cobol-escrow-return-reconciler": "cobol-escrow-return-reconciliation",
}

TAG_ADD = ("debugging", "incremental")


def task_folders() -> list[str]:
    folders = []
    for line in (ROOT / "needs_revision_mapped.txt").read_text().splitlines():
        if line.strip() and not line.startswith("#"):
            _, plat = line.split(None, 1)
            folders.append(ALIASES.get(plat, plat))
    return folders


def fix_dockerfile_copy_slash(task_dir: Path) -> bool:
    dockerfile = task_dir / "environment" / "Dockerfile"
    if not dockerfile.is_file():
        return False
    text = dockerfile.read_text(encoding="utf-8")
    new = re.sub(r"(COPY \S+ /app/[\w./-]+)//+", r"\1/", text)
    if new == text:
        return False
    dockerfile.write_text(new, encoding="utf-8")
    return True


def fix_task_toml_tags(task_dir: Path) -> bool:
    toml = task_dir / "task.toml"
    if not toml.is_file():
        return False
    text = toml.read_text(encoding="utf-8")
    m = re.search(r'^tags = \[(.*?)\]', text, re.MULTILINE)
    if not m:
        return False
    inner = m.group(1)
    tags = [t.strip().strip('"').strip("'") for t in inner.split(",") if t.strip()]
    changed = False
    for tag in TAG_ADD:
        if tag not in tags:
            tags.append(tag)
            changed = True
    if "catering" in tags and "debugging" in tags:
        tags = [t for t in tags if t != "catering"]
        changed = True
    if not changed:
        return False
    quoted = ", ".join(f'"{t}"' for t in tags)
    new = text[: m.start(1)] + quoted + text[m.end(1) :]
    toml.write_text(new, encoding="utf-8")
    return True


def remove_pycache(task_dir: Path) -> int:
    removed = 0
    for p in task_dir.rglob("__pycache__"):
        if p.is_dir():
            for child in sorted(p.rglob("*"), reverse=True):
                if child.is_file():
                    child.unlink()
                    removed += 1
            for child in sorted(p.rglob("*"), reverse=True):
                if child.is_dir():
                    child.rmdir()
            p.rmdir()
            removed += 1
    return removed


def main() -> None:
    changed = []
    for folder in task_folders():
        task_dir = ROOT / folder
        if not task_dir.is_dir():
            print(f"SKIP missing {folder}")
            continue
        edits = []
        if fix_dockerfile_copy_slash(task_dir):
            edits.append("dockerfile")
        if fix_task_toml_tags(task_dir):
            edits.append("tags")
        n = remove_pycache(task_dir)
        if n:
            edits.append(f"pycache({n})")
        if edits:
            changed.append((folder, edits))
            print(f"FIX {folder}: {', '.join(edits)}")
    print(f"\nUpdated {len(changed)} tasks")


if __name__ == "__main__":
    main()
