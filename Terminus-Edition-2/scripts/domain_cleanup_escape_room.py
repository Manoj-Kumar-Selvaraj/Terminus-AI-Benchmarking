#!/usr/bin/env python3
"""Clean remaining source/action wording from the escape-room task."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TASK = ROOT / "go-escape-room-booking-refund-matcher"


PAIRS = [
    ("SOURCE_FILE", "BOOKINGS_FILE"),
    ("ACTION_FILE", "REFUNDS_FILE"),
    ("source_rows", "booking_rows"),
    ("source row", "booking row"),
    ("source rows", "booking rows"),
    ("source order", "booking order"),
    ("source status", "booking status"),
    ("source date", "booking date"),
    ("source dates", "booking dates"),
    ("source amount", "booking amount"),
    ("source input row", "booking input row"),
    ("source input", "booking input"),
    ("source `room_tier`", "booking `room_tier`"),
    ("source slot_date", "booking slot_date"),
    ("source slot", "booking slot"),
    ("action aliases", "refund aliases"),
    ("action alias", "refund alias"),
    ("action-date", "refund-date"),
    ("action input order", "refund input order"),
    ("actions cannot", "refunds cannot"),
    ("duplicate actions", "duplicate refunds"),
    ("action rows", "refund rows"),
    ("action row", "refund row"),
    ("actions_edge.csv", "refunds_edge.csv"),
    ("source_edge.csv", "bookings_edge.csv"),
    ("test_source_status", "test_booking_status"),
    ("current source tree", "current Go tree"),
    ("source tiers", "booking tiers"),
    ("source and refund room_tier", "booking and refund room_tier"),
]


def write_lf(path: Path, text: str) -> None:
    path.write_text(text.replace("\r\n", "\n"), encoding="utf-8", newline="\n")


def clean_text(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    text = text.replace(
        "use the refund's room_tier when matched, and leave `room_tier` blank when no booking matched. ",
        "emit the canonical booking `room_tier` when matched, and leave `room_tier` blank when no booking matched. ",
    )
    for old, new in PAIRS:
        text = text.replace(old, new)
    write_lf(path, text)


def main() -> None:
    for pattern in [
        "steps/milestone_*/instruction.md",
        "steps/milestone_*/tests/test_m*.py",
        "rubric.txt",
        "environment/docs/*.md",
        "environment/config/*.csv",
    ]:
        for path in TASK.glob(pattern):
            clean_text(path)


if __name__ == "__main__":
    main()
