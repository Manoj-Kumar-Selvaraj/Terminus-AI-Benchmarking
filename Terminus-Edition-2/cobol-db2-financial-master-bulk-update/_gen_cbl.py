#!/usr/bin/env python3
"""Regenerate FNBULKUP milestone COBOL sources from shared bridge template."""
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
                   " BRIDGE_FLAGS=" DELIMITED BY SIZE
                   WS-BRIDGE-FLAGS DELIMITED BY SPACE
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

MILESTONES = {
    "broken": {
        "path": ROOT / "environment/src/FNBULKUP.cbl",
        "reject_reason": "BUSINESS_REJECT",
        "flags": {
            "FAIL-CLOSED": "N",
            "REJECT-BUSINESS": "N",
            "REJECT-CONSTRAINT": "N",
            "REJECT-LOCK": "N",
            "CHECK-DUP": "N",
            "SKIP-APPLIED": "N",
            "HANDLE-LOCK": "N",
            "ATOMIC-LIM": "N",
            "CONTROL": "N",
        },
    },
    "m1": {
        "path": ROOT / "steps/milestone_1/solution/FNBULKUP_m1.cbl",
        "reject_reason": "MASTER_ROW_NOT_FOUND",
        "flags": {
            "FAIL-CLOSED": "Y",
            "REJECT-BUSINESS": "Y",
            "REJECT-CONSTRAINT": "N",
            "REJECT-LOCK": "N",
            "CHECK-DUP": "N",
            "SKIP-APPLIED": "N",
            "HANDLE-LOCK": "N",
            "ATOMIC-LIM": "N",
            "CONTROL": "N",
        },
    },
    "m2": {
        "path": ROOT / "steps/milestone_2/solution/FNBULKUP_m2.cbl",
        "reject_reason": "BUSINESS_OR_LOCK_REJECT",
        "flags": {
            "FAIL-CLOSED": "Y",
            "REJECT-BUSINESS": "Y",
            "REJECT-CONSTRAINT": "Y",
            "REJECT-LOCK": "Y",
            "CHECK-DUP": "Y",
            "SKIP-APPLIED": "Y",
            "HANDLE-LOCK": "N",
            "ATOMIC-LIM": "N",
            "CONTROL": "N",
        },
    },
    "m3": {
        "path": ROOT / "steps/milestone_3/solution/FNBULKUP_m3.cbl",
        "reject_reason": "BUSINESS_REJECT",
        "flags": {
            "FAIL-CLOSED": "Y",
            "REJECT-BUSINESS": "Y",
            "REJECT-CONSTRAINT": "Y",
            "REJECT-LOCK": "N",
            "CHECK-DUP": "Y",
            "SKIP-APPLIED": "Y",
            "HANDLE-LOCK": "Y",
            "ATOMIC-LIM": "N",
            "CONTROL": "N",
        },
    },
    "m4": {
        "path": ROOT / "steps/milestone_4/solution/FNBULKUP_m4.cbl",
        "reject_reason": "BUSINESS_REJECT",
        "flags": {
            "FAIL-CLOSED": "Y",
            "REJECT-BUSINESS": "Y",
            "REJECT-CONSTRAINT": "Y",
            "REJECT-LOCK": "N",
            "CHECK-DUP": "Y",
            "SKIP-APPLIED": "Y",
            "HANDLE-LOCK": "Y",
            "ATOMIC-LIM": "Y",
            "CONTROL": "N",
        },
    },
    "m5": {
        "path": ROOT / "steps/milestone_5/solution/FNBULKUP_m5.cbl",
        "reject_reason": "BUSINESS_REJECT",
        "flags": {
            "FAIL-CLOSED": "Y",
            "REJECT-BUSINESS": "Y",
            "REJECT-CONSTRAINT": "Y",
            "REJECT-LOCK": "N",
            "CHECK-DUP": "Y",
            "SKIP-APPLIED": "Y",
            "HANDLE-LOCK": "Y",
            "ATOMIC-LIM": "Y",
            "CONTROL": "Y",
        },
    },
}


def patch_flags(text: str, reject_reason: str, flags: dict[str, str]) -> str:
    text = text.replace(
        '01 WS-REJECT-REASON PIC X(32) VALUE "BUSINESS_REJECT".',
        f'01 WS-REJECT-REASON PIC X(32) VALUE "{reject_reason}".',
    )
    text = text.replace(
        '01 WS-REJECT-REASON PIC X(32) VALUE "BUSINESS_OR_LOCK_REJECT".',
        f'01 WS-REJECT-REASON PIC X(32) VALUE "{reject_reason}".',
    )
    text = text.replace(
        '01 WS-REJECT-REASON PIC X(32) VALUE "MASTER_ROW_NOT_FOUND".',
        f'01 WS-REJECT-REASON PIC X(32) VALUE "{reject_reason}".',
    )
    for name, value in flags.items():
        needle = f'01 WS-FEAT-{name} PIC X VALUE "'
        start = text.find(needle)
        if start == -1:
            raise ValueError(f"missing flag {name}")
        end = text.find('"', start + len(needle))
        text = text[: start + len(needle)] + value + text[end:]
    return text


def replace_bridge_section(text: str) -> str:
    start = text.find("       CALL-IS-APPLIED.")
    end = text.find("       READ-BRIDGE-RESULT.")
    if start == -1 or end == -1:
        raise ValueError("bridge section markers not found")
    end = text.find("\n", text.find(".", end)) + 1
    return text[:start] + BRIDGE_SECTION + text[end:]


def main() -> None:
    base = (ROOT / "steps/milestone_5/solution/FNBULKUP_m5.cbl").read_text()
    for key, cfg in MILESTONES.items():
        out = replace_bridge_section(base)
        out = patch_flags(out, cfg["reject_reason"], cfg["flags"])
        cfg["path"].write_text(out)
        print(f"wrote {cfg['path'].relative_to(ROOT)} ({key})")


if __name__ == "__main__":
    main()
