#!/usr/bin/env python3
"""Normalize escape-room internal team_id naming."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TASK = ROOT / "go-escape-room-booking-refund-matcher"


def write_lf(path: Path, text: str) -> None:
    path.write_text(text.replace("\r\n", "\n"), encoding="utf-8", newline="\n")


def main() -> None:
    for path in list(TASK.glob("steps/milestone_*/solution/*.sh")) + [
        TASK / "steps/milestone_1/tests/test_m1.py",
        TASK / "steps/milestone_2/tests/test_m2.py",
    ]:
        text = path.read_text(encoding="utf-8")
        text = text.replace("Customer, amount", "team_id, amount")
        text = text.replace("test_customer_amount", "test_team_id_amount")
        text = text.replace("TeamIDID", "TeamID")
        text = text.replace("Team:", "TeamID:")
        text = text.replace("Team ", "TeamID ")
        text = text.replace(".Team", ".TeamID")
        text = text.replace(" Team ", " TeamID ")
        text = text.replace("\tTeam\t", "\tTeamID\t")
        text = text.replace("\tTeam ", "\tTeamID ")
        text = text.replace("Team      string", "TeamID    string")
        text = text.replace("Team    string", "TeamID    string")
        write_lf(path, text)


if __name__ == "__main__":
    main()
