#!/usr/bin/env python3
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "cobol-campground-site-deposit-matcher" / "steps"

AMT_OK_VAR = '       01 AMT-OK PIC X VALUE "N".\n'
CHECK_PARA = """
       CHECK-ACTION-AMOUNT.
           MOVE "N" TO AMT-OK
           IF ACT-AMT IS NUMERIC
               MOVE FUNCTION NUMVAL(ACT-AMT) TO WORK-AMOUNT
               IF WORK-AMOUNT > 0
                   MOVE "Y" TO AMT-OK
               END-IF
           END-IF.
"""


def patch_file(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    if "CHECK-ACTION-AMOUNT" in text:
        print(f"skip {path.name}")
        return
    if "01 AMT-OK" not in text:
        text = text.replace(
            "       01 WORK-AMOUNT PIC 9(10) VALUE 0.\n",
            "       01 WORK-AMOUNT PIC 9(10) VALUE 0.\n" + AMT_OK_VAR,
        )
    text = text.replace("\n       PROCESS-ACTION.\n", CHECK_PARA + "\n       PROCESS-ACTION.\n", 1)
    text = text.replace(
        "           PERFORM CHECK-REASON-ELIGIBLE\n           MOVE \"N\" TO MATCHED-FLAG",
        "           PERFORM CHECK-REASON-ELIGIBLE\n           PERFORM CHECK-ACTION-AMOUNT\n           MOVE \"N\" TO MATCHED-FLAG",
    )
    text = re.sub(
        r'IF REASON-OK = "Y"\n(\s+)PERFORM VARYING I',
        r'IF REASON-OK = "Y" AND AMT-OK = "Y"\n\1PERFORM VARYING I',
        text,
        count=1,
    )
    text = text.replace(
        "           MOVE ACT-AMT TO WORK-AMOUNT\n           IF MATCHED-FLAG = \"Y\"",
        "           MOVE 0 TO WORK-AMOUNT\n           IF AMT-OK = \"Y\"\n"
        "               MOVE FUNCTION NUMVAL(ACT-AMT) TO WORK-AMOUNT\n           END-IF\n"
        "           IF MATCHED-FLAG = \"Y\"",
    )
    path.write_text(text, encoding="utf-8")
    print(f"patched {path.name}")


def main() -> None:
    for m in range(2, 6):
        patch_file(ROOT / f"milestone_{m}/solution/oracle_m{m}.cbl")


if __name__ == "__main__":
    main()
