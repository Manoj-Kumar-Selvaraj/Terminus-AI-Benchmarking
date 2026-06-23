#!/usr/bin/env python3
"""Patch FNBULKUP.cbl milestone variants with fixed bridge command builders."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent

BRIDGE_SECTION = """\
       CALL-IS-APPLIED.
           MOVE SPACES TO WS-CMD-LINE
           STRING "bash /app/bin/finbulk_op.sh is-applied BRIDGE_BATCH="
               WS-BATCH-ID DELIMITED BY SPACE
               " BRIDGE_SEQ=" WS-SEQ DELIMITED BY SIZE
               INTO WS-CMD-LINE
           END-STRING
           CALL "SYSTEM" USING WS-CMD-LINE
           PERFORM READ-BRIDGE-RESULT
           IF WS-BRIDGE-RESULT(1:1) = "1"
               MOVE "Y" TO WS-APPLIED-FLAG
           ELSE
               MOVE "N" TO WS-APPLIED-FLAG
           END-IF
           .

       CALL-APPLY-DETAIL.
           MOVE SPACES TO WS-CMD-LINE
           STRING "bash /app/bin/finbulk_op.sh apply-detail BRIDGE_BATCH="
               WS-BATCH-ID DELIMITED BY SPACE
               " BRIDGE_SEQ=" WS-SEQ DELIMITED BY SIZE
               " BRIDGE_ACCOUNT=" WS-ACCOUNT DELIMITED BY SPACE
               " BRIDGE_OP=" WS-OP DELIMITED BY SPACE
               " BRIDGE_AMOUNT=" WS-AMOUNT DELIMITED BY SIZE
               " BRIDGE_EVENT_ID=" WS-EVENT-ID DELIMITED BY SPACE
               INTO WS-CMD-LINE
           END-STRING
           IF WS-BRIDGE-FLAGS NOT = SPACES
               STRING WS-CMD-LINE DELIMITED BY SIZE
                   " BRIDGE_FLAGS=" WS-BRIDGE-FLAGS DELIMITED BY SPACE
                   INTO WS-CMD-LINE
               END-STRING
           END-IF
           CALL "SYSTEM" USING WS-CMD-LINE
           PERFORM READ-BRIDGE-RESULT
           MOVE FUNCTION NUMVAL(FUNCTION TRIM(WS-BRIDGE-RESULT)) TO WS-SQLCODE
           .

       CALL-APPEND-REJECT.
           MOVE SPACES TO WS-CMD-LINE
           STRING "bash /app/bin/finbulk_op.sh append-reject BRIDGE_BATCH="
               WS-BATCH-ID DELIMITED BY SPACE
               " BRIDGE_SEQ=" WS-SEQ DELIMITED BY SIZE
               " BRIDGE_ACCOUNT=" WS-ACCOUNT DELIMITED BY SPACE
               " BRIDGE_SQLCODE=" WS-SQLCODE DELIMITED BY SIZE
               " BRIDGE_REASON=" WS-REJECT-REASON DELIMITED BY SPACE
               " BRIDGE_EVENT_ID=" WS-EVENT-ID DELIMITED BY SPACE
               INTO WS-CMD-LINE
           END-STRING
           CALL "SYSTEM" USING WS-CMD-LINE
           .

       CALL-APPEND-PENDING-LOCK.
           MOVE SPACES TO WS-CMD-LINE
           STRING "bash /app/bin/finbulk_op.sh append-pending-lock BRIDGE_BATCH="
               WS-BATCH-ID DELIMITED BY SPACE
               " BRIDGE_SEQ=" WS-SEQ DELIMITED BY SIZE
               " BRIDGE_ACCOUNT=" WS-ACCOUNT DELIMITED BY SPACE
               " BRIDGE_EVENT_ID=" WS-EVENT-ID DELIMITED BY SPACE
               INTO WS-CMD-LINE
           END-STRING
           CALL "SYSTEM" USING WS-CMD-LINE
           .

       DO-SAVE-DB.
           MOVE SPACES TO WS-CMD-LINE
           STRING "bash /app/bin/finbulk_op.sh save BRIDGE_BATCH="
               WS-BATCH-ID DELIMITED BY SPACE
               INTO WS-CMD-LINE
           END-STRING
           CALL "SYSTEM" USING WS-CMD-LINE
           .

       DO-WRITE-OUTPUTS.
           MOVE SPACES TO WS-CMD-LINE
           STRING "bash /app/bin/finbulk_op.sh write-outputs BRIDGE_BATCH="
               WS-BATCH-ID DELIMITED BY SPACE
               " BRIDGE_STATUS=" WS-STATUS DELIMITED BY SPACE
               " BRIDGE_APPLIED=" WS-APPLIED DELIMITED BY SIZE
               " BRIDGE_REJECTED=" WS-REJECTED DELIMITED BY SIZE
               " BRIDGE_SKIPPED=" WS-SKIPPED DELIMITED BY SIZE
               " BRIDGE_PENDING_LOCKS=" WS-PENDING-LOCKS DELIMITED BY SIZE
               " BRIDGE_LAST_SQLCODE=" WS-LAST-SQLCODE DELIMITED BY SIZE
               INTO WS-CMD-LINE
           END-STRING
           CALL "SYSTEM" USING WS-CMD-LINE
           .

       DO-FAILED-CLOSED.
           IF WS-BATCH-ID = SPACES
               MOVE "UNKNOWN" TO WS-BATCH-ID
           END-IF
           MOVE SPACES TO WS-CMD-LINE
           STRING "bash /app/bin/finbulk_op.sh failed-closed BRIDGE_BATCH="
               WS-BATCH-ID DELIMITED BY SPACE
               " BRIDGE_ERROR=" WS-ERROR-MSG DELIMITED BY SPACE
               INTO WS-CMD-LINE
           END-STRING
           CALL "SYSTEM" USING WS-CMD-LINE
           .

       DO-VALIDATE-CONTROL.
           MOVE SPACES TO WS-CMD-LINE
           STRING "bash /app/bin/finbulk_op.sh validate-control BRIDGE_BATCH="
               WS-BATCH-ID DELIMITED BY SPACE
               " BRIDGE_INPUT=" FINBULK-INPUT-NAME DELIMITED BY SPACE
               " BRIDGE_CONTROL=" FINBULK-CONTROL DELIMITED BY SPACE
               INTO WS-CMD-LINE
           END-STRING
           CALL "SYSTEM" USING WS-CMD-LINE
           PERFORM READ-BRIDGE-RESULT
           IF FUNCTION LENGTH(FUNCTION TRIM(WS-BRIDGE-RESULT)) NOT = 64
               MOVE FUNCTION TRIM(WS-BRIDGE-RESULT) TO WS-ERROR-MSG
           ELSE
               MOVE FUNCTION TRIM(WS-BRIDGE-RESULT) TO WS-INPUT-HASH
           END-IF
           .

       DO-ENFORCE-CONTROL.
           MOVE SPACES TO WS-CMD-LINE
           STRING "bash /app/bin/finbulk_op.sh enforce-control-replay BRIDGE_BATCH="
               WS-BATCH-ID DELIMITED BY SPACE
               " BRIDGE_INPUT_HASH=" WS-INPUT-HASH DELIMITED BY SPACE
               INTO WS-CMD-LINE
           END-STRING
           CALL "SYSTEM" USING WS-CMD-LINE
           PERFORM READ-BRIDGE-RESULT
           IF FUNCTION TRIM(WS-BRIDGE-RESULT) NOT = "0"
               MOVE FUNCTION TRIM(WS-BRIDGE-RESULT) TO WS-ERROR-MSG
           END-IF
           .

       DO-RECORD-CONTROL.
           MOVE SPACES TO WS-CMD-LINE
           STRING "bash /app/bin/finbulk_op.sh record-control-total BRIDGE_BATCH="
               WS-BATCH-ID DELIMITED BY SPACE
               " BRIDGE_INPUT_HASH=" WS-INPUT-HASH DELIMITED BY SPACE
               " BRIDGE_CONTROL=" FINBULK-CONTROL DELIMITED BY SPACE
               " BRIDGE_STATUS=" WS-STATUS DELIMITED BY SPACE
               " BRIDGE_PENDING_LOCKS=" WS-PENDING-LOCKS DELIMITED BY SIZE
               INTO WS-CMD-LINE
           END-STRING
           CALL "SYSTEM" USING WS-CMD-LINE
           .

       READ-BRIDGE-RESULT.
           OPEN INPUT BRIDGE-FILE
           READ BRIDGE-FILE INTO WS-BRIDGE-RESULT
           CLOSE BRIDGE-FILE
           .
"""

VARIANTS = {
    "environment/src/FNBULKUP.cbl": ("BUSINESS_REJECT", "N", "N", "N", "N", "N", "N", "N", "N", "N"),
    "steps/milestone_1/solution/FNBULKUP_m1.cbl": ("MASTER_ROW_NOT_FOUND", "Y", "Y", "N", "N", "N", "N", "N", "N", "N"),
    "steps/milestone_2/solution/FNBULKUP_m2.cbl": ("BUSINESS_OR_LOCK_REJECT", "Y", "Y", "Y", "Y", "Y", "Y", "N", "N", "N"),
    "steps/milestone_3/solution/FNBULKUP_m3.cbl": ("BUSINESS_REJECT", "Y", "Y", "Y", "N", "Y", "Y", "Y", "N", "N"),
    "steps/milestone_4/solution/FNBULKUP_m4.cbl": ("BUSINESS_REJECT", "Y", "Y", "Y", "N", "Y", "Y", "Y", "Y", "N"),
    "steps/milestone_5/solution/FNBULKUP_m5.cbl": ("BUSINESS_REJECT", "Y", "Y", "Y", "N", "Y", "Y", "Y", "Y", "Y"),
}


def patch_file(rel_path: str, cfg: tuple[str, ...]) -> None:
    path = ROOT / rel_path
    text = path.read_text()
    start = text.index("       CALL-IS-APPLIED.")
    end = text.index("       READ-BRIDGE-RESULT.")
    end = text.index(".", end) + 2
    text = text[:start] + BRIDGE_SECTION + text[end:]

    reason, fail, biz, constr, lock, dup, skip, hlock, atomic, control = cfg
    lines = text.splitlines()
    out: list[str] = []
    for line in lines:
        if "WS-REJECT-REASON PIC" in line:
            out.append(f'       01 WS-REJECT-REASON PIC X(32) VALUE "{reason}".')
        elif "WS-FEAT-FAIL-CLOSED PIC" in line:
            out.append(f'       01 WS-FEAT-FAIL-CLOSED PIC X VALUE "{fail}".')
        elif "WS-FEAT-REJECT-BUSINESS PIC" in line:
            out.append(f'       01 WS-FEAT-REJECT-BUSINESS PIC X VALUE "{biz}".')
        elif "WS-FEAT-REJECT-CONSTRAINT PIC" in line:
            out.append(f'       01 WS-FEAT-REJECT-CONSTRAINT PIC X VALUE "{constr}".')
        elif "WS-FEAT-REJECT-LOCK PIC" in line:
            out.append(f'       01 WS-FEAT-REJECT-LOCK PIC X VALUE "{lock}".')
        elif "WS-FEAT-CHECK-DUP PIC" in line:
            out.append(f'       01 WS-FEAT-CHECK-DUP PIC X VALUE "{dup}".')
        elif "WS-FEAT-SKIP-APPLIED PIC" in line:
            out.append(f'       01 WS-FEAT-SKIP-APPLIED PIC X VALUE "{skip}".')
        elif "WS-FEAT-HANDLE-LOCK PIC" in line:
            out.append(f'       01 WS-FEAT-HANDLE-LOCK PIC X VALUE "{hlock}".')
        elif "WS-FEAT-ATOMIC-LIM PIC" in line:
            out.append(f'       01 WS-FEAT-ATOMIC-LIM PIC X VALUE "{atomic}".')
        elif "WS-FEAT-CONTROL PIC" in line:
            out.append(f'       01 WS-FEAT-CONTROL PIC X VALUE "{control}".')
        else:
            out.append(line)
    path.write_text("\n".join(out) + "\n")
    print(f"Patched {rel_path}")


def main() -> None:
    for rel, cfg in VARIANTS.items():
        patch_file(rel, cfg)


if __name__ == "__main__":
    main()
