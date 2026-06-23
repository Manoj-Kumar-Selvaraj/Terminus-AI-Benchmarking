#!/usr/bin/env python3
"""Normalize escape-room task output filenames to booking/refund terminology."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TASK = ROOT / "go-escape-room-booking-refund-matcher"


def write_lf(path: Path, text: str) -> None:
    path.write_text(text.replace("\r\n", "\n"), encoding="utf-8", newline="\n")


def main() -> None:
    for path in TASK.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix in {".pyc", ".zip", ".tar", ".gz"}:
            continue
        text = path.read_text(encoding="utf-8")
        updated = text.replace("escape_refund_report.csv", "booking_refund_report.csv")
        updated = updated.replace("escape_refund_summary.json", "booking_refund_summary.json")
        if updated != text:
            write_lf(path, updated)


if __name__ == "__main__":
    main()
