#!/usr/bin/env python3
"""Rename escape-room starter/solution internals into the task domain."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TASK = ROOT / "go-escape-room-booking-refund-matcher"


REPLACEMENTS = [
    ("canonicalPassType", "canonicalRoomTier"),
    ("allowedPassType", "allowedRoomTier"),
    ("HasRefundDate", "HasRefundDate"),
    ("RefundDate", "RefundDate"),
    ("HasSlotDate", "HasSlotDate"),
    ("SlotDate", "SlotDate"),
    ("PassType", "RoomTier"),
    ("pass_type", "roomTier"),
    ("TripID", "BookingID"),
    ("Customer", "Team"),
    ("Credit", "Refund"),
    ("credit", "refund"),
    ("credits", "refunds"),
    ("loadCredits", "loadRefunds"),
    ("Trip", "Booking"),
    ("trip", "booking"),
    ("trips", "bookings"),
]


def write_lf(path: Path, text: str) -> None:
    path.write_text(text.replace("\r\n", "\n"), encoding="utf-8", newline="\n")


def apply_replacements(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    for old, new in REPLACEMENTS:
        text = text.replace(old, new)
    write_lf(path, text)


def clean_instructions() -> None:
    for path in TASK.glob("steps/milestone_*/instruction.md"):
        text = path.read_text(encoding="utf-8")
        lines = [
            line
            for line in text.splitlines()
            if not line.startswith("The starter intentionally uses internal names")
            and "starter source intentionally uses legacy internal identifiers" not in line
        ]
        support_note = (
            "Support files `config/methods.csv`, `samples/source_edge.csv`, and "
            "`samples/actions_edge.csv` are legacy reference filenames and do not change "
            "the required booking/refund CSV schemas."
        )
        text = "\n".join(lines).rstrip()
        if support_note not in text:
            text += "\n\n" + support_note
        write_lf(path, text + "\n")

    operations = TASK / "environment/docs/operations.md"
    text = operations.read_text(encoding="utf-8")
    text = text.replace(
        "The starter Go source intentionally contains legacy generic identifiers such as Trip, Credit, Customer, and PassType; those names are part of the buggy implementation surface. The CSV headers and task instructions are authoritative for required behavior.\n\n",
        "The reconciliation job uses booking/refund domain names in the Go source. The CSV headers and task instructions are authoritative for required behavior.\n\n",
    )
    write_lf(operations, text)


def main() -> None:
    apply_replacements(TASK / "environment/cmd/reconcile/main.go")
    for path in TASK.glob("steps/milestone_*/solution/*.sh"):
        apply_replacements(path)
    clean_instructions()


if __name__ == "__main__":
    main()
