#!/usr/bin/env python3
"""Load LOCAL_OK tasks from portal_ids_manifest.tsv."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "Revision-ChatGpt" / "needs_revision_pulls" / "portal_ids_manifest.tsv"


def load_manifest() -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    for line in MANIFEST.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        sid, folder, status = line.split("\t")
        if status == "LOCAL_OK":
            rows.append((sid, folder))
    return rows


if __name__ == "__main__":
    for sid, folder in load_manifest():
        print(f"{sid}\t{folder}")
