#!/usr/bin/env python3
"""Generate FNBULKUP.cbl variants from shared template and milestone feature flags."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

VARIANTS: dict[str, dict[str, str]] = {
    "broken": {
        "path": ROOT / "environment" / "src" / "FNBULKUP.cbl",
        "reject_reason": "BUSINESS_REJECT",
        "fail_closed": "N",
        "reject_business": "N",
        "reject_constraint": "N",
        "reject_lock": "N",
        "check_dup": "N",
        "skip_applied": "N",
        "handle_lock": "N",
        "atomic_lim": "N",
        "control": "N",
    },
    "m1": {
        "path": ROOT / "steps" / "milestone_1" / "solution" / "FNBULKUP_m1.cbl",
        "reject_reason": "MASTER_ROW_NOT_FOUND",
        "fail_closed": "Y",
        "reject_business": "Y",
        "reject_constraint": "N",
        "reject_lock": "N",
        "check_dup": "N",
        "skip_applied": "N",
        "handle_lock": "N",
        "atomic_lim": "N",
        "control": "N",
    },
    "m2": {
        "path": ROOT / "steps" / "milestone_2" / "solution" / "FNBULKUP_m2.cbl",
        "reject_reason": "BUSINESS_OR_LOCK_REJECT",
        "fail_closed": "Y",
        "reject_business": "Y",
        "reject_constraint": "Y",
        "reject_lock": "Y",
        "check_dup": "Y",
        "skip_applied": "Y",
        "handle_lock": "N",
        "atomic_lim": "N",
        "control": "N",
    },
    "m3": {
        "path": ROOT / "steps" / "milestone_3" / "solution" / "FNBULKUP_m3.cbl",
        "reject_reason": "BUSINESS_REJECT",
        "fail_closed": "Y",
        "reject_business": "Y",
        "reject_constraint": "Y",
        "reject_lock": "N",
        "check_dup": "Y",
        "skip_applied": "Y",
        "handle_lock": "Y",
        "atomic_lim": "N",
        "control": "N",
    },
    "m4": {
        "path": ROOT / "steps" / "milestone_4" / "solution" / "FNBULKUP_m4.cbl",
        "reject_reason": "BUSINESS_REJECT",
        "fail_closed": "Y",
        "reject_business": "Y",
        "reject_constraint": "Y",
        "reject_lock": "N",
        "check_dup": "Y",
        "skip_applied": "Y",
        "handle_lock": "Y",
        "atomic_lim": "Y",
        "control": "N",
    },
    "m5": {
        "path": ROOT / "steps" / "milestone_5" / "solution" / "FNBULKUP_m5.cbl",
        "reject_reason": "BUSINESS_REJECT",
        "fail_closed": "Y",
        "reject_business": "Y",
        "reject_constraint": "Y",
        "reject_lock": "N",
        "check_dup": "Y",
        "skip_applied": "Y",
        "handle_lock": "Y",
        "atomic_lim": "Y",
        "control": "Y",
    },
}

TEMPLATE = """\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. FNBULKUP.
*> COBOL batch driver for FINUPD fixed-width bulk updates.
*> DB2 semantics are provided by /app/tools/db2_bridge.py via finbulk_op.sh.
       ENVIRONMENT DIVISION.
       INPUT-OUTPUT SECTION.
       FILE-CONTROL.
           SELECT IN-FILE ASSIGN TO DYNAMIC FINBULK-INPUT-NAME
               ORGANIZATION IS LINE SEQUENTIAL.
           SELECT BRIDGE-FILE ASSIGN TO "/tmp/finbulk_bridge.out"
               ORGANIZATION IS LINE SEQUENTIAL.
       DATA DIVISION.
       FILE SECTION.
       FD IN-FILE.
       01 IN-LINE PIC X(256).
       FD BRIDGE-FILE.
       01 BRIDGE-LINE PIC X(512).
       WORKING-STORAGE SECTION.
       COPY "FINUPD.cpy".
       01 FINBULK-INPUT-NAME PIC X(512).
       01 FINBULK-DB PIC X(512).
       01 FINBULK-OUT PIC X(512).
       01 FINBULK-BATCH-ENV PIC X(32).
       01 FINBULK-ABEND-AFTER PIC X(16).
       01 FINBULK-CONTROL PIC X(512).
       01 WS-BATCH-ID PIC X(10).
       01 WS-ABEND-AFTER PIC 9(9) VALUE 0.
       01 WS-EOF PIC X VALUE "N".
       01 WS-LINE-COUNT PIC 9(9) VALUE 0.
       01 WS-DETAIL-COUNT PIC 9(9) VALUE 0.
       01 WS-BAL-TOTAL PIC S9(18) VALUE 0.
       01 WS-TRAILER-TOTAL PIC S9(18) VALUE 0.
       01 WS-APPLIED PIC 9(9) VALUE 0.
       01 WS-REJECTED PIC 9(9) VALUE 0.
       01 WS-SKIPPED PIC 9(9) VALUE 0.
       01 WS-PENDING-LOCKS PIC 9(9) VALUE 0.
       01 WS-STATUS PIC X(16) VALUE "OK".
       01 WS-LAST-SQLCODE PIC S9(9) VALUE 0.
       01 WS-ERROR-MSG PIC X(256).
       01 WS-INPUT-HASH PIC X(64).
       01 WS-REJECT-REASON PIC X(32) VALUE "{reject_reason}".
       01 WS-BRIDGE-RESULT PIC X(512).
       01 WS-CMD-LINE PIC X(4096).
       01 WS-SEQ PIC 9(6).
       01 WS-ACCOUNT PIC X(12).
       01 WS-OP PIC X(3).
       01 WS-AMOUNT PIC S9(18).
       01 WS-EVENT-ID PIC X(8).
       01 WS-SQLCODE PIC S9(9).
       01 WS-APPLIED-FLAG PIC X.
       01 WS-I PIC 9(9).
       01 WS-J PIC 9(9).
       01 WS-AMT-WORK PIC 9(12).
       01 WS-SIGN PIC X.
       01 WS-RETURN-CODE PIC 9(4) VALUE 0.
       01 WS-FEAT-FAIL-CLOSED PIC X VALUE "{fail_closed}".
       01 WS-FEAT-REJECT-BUSINESS PIC X VALUE "{reject_business}".
       01 WS-FEAT-REJECT-CONSTRAINT PIC X VALUE "{reject_constraint}".
       01 WS-FEAT-REJECT-LOCK PIC X VALUE "{reject_lock}".
       01 WS-FEAT-CHECK-DUP PIC X VALUE "{check_dup}".
       01 WS-FEAT-SKIP-APPLIED PIC X VALUE "{skip_applied}".
       01 WS-FEAT-HANDLE-LOCK PIC X VALUE "{handle_lock}".
       01 WS-FEAT-ATOMIC-LIM PIC X VALUE "{atomic_lim}".
       01 WS-FEAT-CONTROL PIC X VALUE "{control}".
       01 WS-BRIDGE-FLAGS PIC X(64).
       01 WS-DETAIL-TABLE.
          05 WS-DETAIL-ROW OCCURS 500 TIMES.
             10 WS-D-SEQ PIC 9(6).
             10 WS-D-ACCOUNT PIC X(12).
             10 WS-D-OP PIC X(3).
             10 WS-D-AMOUNT PIC S9(18).
             10 WS-D-EVENT PIC X(8).
       PROCEDURE DIVISION.
       MAIN-PARA.
           PERFORM INIT-ENV
           PERFORM READ-INPUT-FILE
           IF WS-FEAT-FAIL-CLOSED = "Y"
               PERFORM VALIDATE-STRICT
               IF WS-ERROR-MSG NOT = SPACES
                   PERFORM DO-FAILED-CLOSED
                   MOVE 2 TO RETURN-CODE
                   STOP RUN
               END-IF
           ELSE
               PERFORM VALIDATE-BASIC
               IF WS-ERROR-MSG NOT = SPACES
                   DISPLAY WS-ERROR-MSG
                   MOVE 99 TO RETURN-CODE
                   STOP RUN
               END-IF
           END-IF
           IF WS-FEAT-CONTROL = "Y"
              AND FINBULK-CONTROL NOT = SPACES
               PERFORM DO-VALIDATE-CONTROL
               IF WS-ERROR-MSG NOT = SPACES
                   PERFORM DO-FAILED-CLOSED
                   MOVE 2 TO RETURN-CODE
                   STOP RUN
               END-IF
               PERFORM DO-ENFORCE-CONTROL
               IF WS-ERROR-MSG NOT = SPACES
                   PERFORM DO-FAILED-CLOSED
                   MOVE 2 TO RETURN-CODE
                   STOP RUN
               END-IF
           END-IF
           PERFORM PROCESS-DETAILS
           IF WS-FEAT-CONTROL = "Y"
              AND FINBULK-CONTROL NOT = SPACES
              AND WS-RETURN-CODE = 0
               PERFORM DO-RECORD-CONTROL
           END-IF
           IF WS-RETURN-CODE = 0
               PERFORM DO-WRITE-OUTPUTS
           END-IF
           MOVE WS-RETURN-CODE TO RETURN-CODE
           STOP RUN.

       INIT-ENV.
           ACCEPT FINBULK-INPUT-NAME FROM ENVIRONMENT "FINBULK_INPUT"
           ACCEPT FINBULK-DB FROM ENVIRONMENT "FINBULK_DB"
           ACCEPT FINBULK-OUT FROM ENVIRONMENT "FINBULK_OUT"
           ACCEPT FINBULK-BATCH-ENV FROM ENVIRONMENT "FINBULK_BATCH"
           ACCEPT FINBULK-ABEND-AFTER FROM ENVIRONMENT "FINBULK_ABEND_AFTER"
           ACCEPT FINBULK-CONTROL FROM ENVIRONMENT "FINBULK_CONTROL"
           IF FINBULK-ABEND-AFTER IS NUMERIC
               MOVE FINBULK-ABEND-AFTER TO WS-ABEND-AFTER
           END-IF
           MOVE SPACES TO WS-ERROR-MSG
           MOVE SPACES TO WS-BRIDGE-FLAGS
           IF WS-FEAT-CHECK-DUP = "Y"
               MOVE "check-duplicate" TO WS-BRIDGE-FLAGS
           END-IF
           IF WS-FEAT-ATOMIC-LIM = "Y"
               IF WS-BRIDGE-FLAGS = SPACES
                   MOVE "atomic-lim" TO WS-BRIDGE-FLAGS
               ELSE
                   STRING WS-BRIDGE-FLAGS ",atomic-lim"
                       DELIMITED BY SIZE INTO WS-BRIDGE-FLAGS
               END-STRING
           END-IF
           CALL "SYSTEM" USING "mkdir -p /tmp"
           .

       READ-INPUT-FILE.
           OPEN INPUT IN-FILE
           PERFORM UNTIL WS-EOF = "Y"
               READ IN-FILE
                   AT END MOVE "Y" TO WS-EOF
                   NOT AT END
                       ADD 1 TO WS-LINE-COUNT
                       IF WS-LINE-COUNT = 1
                           MOVE IN-LINE TO FINUPD-HEADER
                           IF HDR-REC-TYPE NOT = "H"
                               MOVE "missing header or trailer"
                                   TO WS-ERROR-MSG
                           ELSE
                               MOVE HDR-BATCH-ID TO WS-BATCH-ID
                           END-IF
                       ELSE
                           IF IN-LINE(1:1) = "T"
                               MOVE IN-LINE TO FINUPD-TRAILER
                           ELSE
                               IF IN-LINE(1:1) NOT = "D"
                                   MOVE "bad record type" TO WS-ERROR-MSG
                               ELSE
                                   IF WS-DETAIL-COUNT >= 500
                                       MOVE "too many details"
                                           TO WS-ERROR-MSG
                                   ELSE
                                       MOVE IN-LINE TO FINUPD-DETAIL
                                       IF DTL-SEQUENCE NOT NUMERIC
                                           MOVE "malformed detail record"
                                               TO WS-ERROR-MSG
                                       ELSE
                                           IF DTL-AMOUNT-SIGN NOT = "+"
                                              AND DTL-AMOUNT-SIGN NOT = "-"
                                               MOVE "malformed detail record"
                                                   TO WS-ERROR-MSG
                                           ELSE
                                               ADD 1 TO WS-DETAIL-COUNT
                                               MOVE DTL-SEQUENCE
                                                   TO WS-D-SEQ(WS-DETAIL-COUNT)
                                               MOVE DTL-ACCOUNT-ID
                                                   TO WS-D-ACCOUNT(WS-DETAIL-COUNT)
                                               MOVE DTL-OP-CODE
                                                   TO WS-D-OP(WS-DETAIL-COUNT)
                                               MOVE DTL-EVENT-ID
                                                   TO WS-D-EVENT(WS-DETAIL-COUNT)
                                               MOVE DTL-AMOUNT-SIGN TO WS-SIGN
                                               MOVE DTL-AMOUNT-CENTS TO WS-AMT-WORK
                                               IF WS-SIGN = "-"
                                                   COMPUTE WS-D-AMOUNT(WS-DETAIL-COUNT)
                                                       = WS-AMT-WORK * -1
                                               ELSE
                                                   MOVE WS-AMT-WORK
                                                       TO WS-D-AMOUNT(WS-DETAIL-COUNT)
                                               END-IF
                                               IF WS-D-OP(WS-DETAIL-COUNT) = "BAL"
                                                   ADD WS-D-AMOUNT(WS-DETAIL-COUNT)
                                                       TO WS-BAL-TOTAL
                                               END-IF
                                           END-IF
                                       END-IF
                                   END-IF
                               END-IF
                           END-IF
                       END-IF
               END-READ
           END-PERFORM
           CLOSE IN-FILE
           IF WS-LINE-COUNT < 2
               MOVE "missing header or trailer" TO WS-ERROR-MSG
           END-IF
           IF TRL-REC-TYPE NOT = "T"
               MOVE "missing header or trailer" TO WS-ERROR-MSG
           END-IF
           IF FINBULK-BATCH-ENV NOT = SPACES
               MOVE FINBULK-BATCH-ENV TO WS-BATCH-ID
           END-IF
           .

       VALIDATE-BASIC.
           IF WS-ERROR-MSG NOT = SPACES
               CONTINUE
           END-IF
           IF HDR-BATCH-ID NOT = TRL-BATCH-ID
               MOVE "header/trailer batch mismatch" TO WS-ERROR-MSG
           END-IF
           IF WS-DETAIL-COUNT NOT = TRL-DETAIL-COUNT
               MOVE "trailer count mismatch" TO WS-ERROR-MSG
           END-IF
           .

       VALIDATE-STRICT.
           PERFORM VALIDATE-BASIC
           IF WS-ERROR-MSG NOT = SPACES
               GO TO VALIDATE-STRICT-EXIT
           END-IF
           MOVE TRL-TOTAL-SIGN TO WS-SIGN
           MOVE TRL-TOTAL-CENTS TO WS-AMT-WORK
           IF WS-SIGN = "-"
               COMPUTE WS-TRAILER-TOTAL = WS-AMT-WORK * -1
           ELSE
               IF WS-SIGN = "+"
                   MOVE WS-AMT-WORK TO WS-TRAILER-TOTAL
               ELSE
                   MOVE "bad signed amount" TO WS-ERROR-MSG
                   GO TO VALIDATE-STRICT-EXIT
               END-IF
           END-IF
           IF WS-BAL-TOTAL NOT = WS-TRAILER-TOTAL
               MOVE "trailer financial total mismatch"
                   TO WS-ERROR-MSG
               GO TO VALIDATE-STRICT-EXIT
           END-IF
           PERFORM VARYING WS-I FROM 1 BY 1 UNTIL WS-I > WS-DETAIL-COUNT
               IF WS-D-SEQ(WS-I) <= 0
                   MOVE "malformed detail record" TO WS-ERROR-MSG
                   GO TO VALIDATE-STRICT-EXIT
               END-IF
               IF WS-D-ACCOUNT(WS-I) = SPACES
                   MOVE "malformed detail record" TO WS-ERROR-MSG
                   GO TO VALIDATE-STRICT-EXIT
               END-IF
               IF WS-D-OP(WS-I) NOT = "BAL"
                  AND WS-D-OP(WS-I) NOT = "RAT"
                  AND WS-D-OP(WS-I) NOT = "HLD"
                  AND WS-D-OP(WS-I) NOT = "LIM"
                   MOVE "malformed detail record" TO WS-ERROR-MSG
                   GO TO VALIDATE-STRICT-EXIT
               END-IF
               PERFORM VARYING WS-J FROM 1 BY 1 UNTIL WS-J >= WS-I
                   IF WS-D-SEQ(WS-J) = WS-D-SEQ(WS-I)
                       MOVE "duplicate sequence in control file"
                           TO WS-ERROR-MSG
                       GO TO VALIDATE-STRICT-EXIT
                   END-IF
               END-PERFORM
           END-PERFORM
           .
       VALIDATE-STRICT-EXIT.
           EXIT.

       PROCESS-DETAILS.
           PERFORM VARYING WS-I FROM 1 BY 1
               UNTIL WS-I > WS-DETAIL-COUNT OR WS-RETURN-CODE NOT = 0
               MOVE WS-D-SEQ(WS-I) TO WS-SEQ
               MOVE WS-D-ACCOUNT(WS-I) TO WS-ACCOUNT
               MOVE WS-D-OP(WS-I) TO WS-OP
               MOVE WS-D-AMOUNT(WS-I) TO WS-AMOUNT
               MOVE WS-D-EVENT(WS-I) TO WS-EVENT-ID
               IF WS-FEAT-SKIP-APPLIED = "Y"
                   PERFORM CALL-IS-APPLIED
                   IF WS-APPLIED-FLAG = "Y"
                       ADD 1 TO WS-SKIPPED
                       GO TO PROCESS-NEXT-DETAIL
                   END-IF
               END-IF
               PERFORM CALL-APPLY-DETAIL
               IF WS-SQLCODE = 0
                   ADD 1 TO WS-APPLIED
                   IF WS-ABEND-AFTER > 0
                      AND WS-APPLIED >= WS-ABEND-AFTER
                       MOVE "SIMULATED_ABEND" TO WS-STATUS
                       PERFORM DO-SAVE-DB
                       PERFORM DO-WRITE-OUTPUTS
                       MOVE 66 TO WS-RETURN-CODE
                       GO TO PROCESS-DETAILS-EXIT
                   END-IF
               ELSE
                   IF WS-FEAT-SKIP-APPLIED = "Y"
                      AND WS-SQLCODE = -803
                       ADD 1 TO WS-SKIPPED
                       GO TO PROCESS-NEXT-DETAIL
                   END-IF
                   IF WS-FEAT-HANDLE-LOCK = "Y"
                      AND WS-SQLCODE = -911
                       PERFORM CALL-APPEND-PENDING-LOCK
                       ADD 1 TO WS-PENDING-LOCKS
                       MOVE "RETRYABLE_LOCK" TO WS-STATUS
                       PERFORM DO-SAVE-DB
                       PERFORM DO-WRITE-OUTPUTS
                       MOVE 75 TO WS-RETURN-CODE
                       GO TO PROCESS-DETAILS-EXIT
                   END-IF
                   IF WS-FEAT-REJECT-BUSINESS = "Y"
                      AND WS-SQLCODE = 100
                       PERFORM CALL-APPEND-REJECT
                       ADD 1 TO WS-REJECTED
                       GO TO PROCESS-NEXT-DETAIL
                   END-IF
                   IF WS-FEAT-REJECT-CONSTRAINT = "Y"
                      AND WS-SQLCODE = -530
                       PERFORM CALL-APPEND-REJECT
                       ADD 1 TO WS-REJECTED
                       GO TO PROCESS-NEXT-DETAIL
                   END-IF
                   IF WS-FEAT-REJECT-LOCK = "Y"
                      AND WS-SQLCODE = -911
                       PERFORM CALL-APPEND-REJECT
                       ADD 1 TO WS-REJECTED
                       GO TO PROCESS-NEXT-DETAIL
                   END-IF
                   MOVE WS-SQLCODE TO WS-LAST-SQLCODE
                   MOVE "ABEND" TO WS-STATUS
                   PERFORM DO-SAVE-DB
                   PERFORM DO-WRITE-OUTPUTS
                   MOVE 12 TO WS-RETURN-CODE
                   GO TO PROCESS-DETAILS-EXIT
               END-IF
           END-PERFORM
           PERFORM DO-SAVE-DB
           .
       PROCESS-NEXT-DETAIL.
           CONTINUE.
       PROCESS-DETAILS-EXIT.
           EXIT.

       CALL-IS-APPLIED.
           MOVE SPACES TO WS-CMD-LINE
           STRING "bash /app/bin/finbulk_op.sh is-applied "
               "BRIDGE_SEQ=" WS-SEQ DELIMITED BY SIZE
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
           STRING "bash /app/bin/finbulk_op.sh apply-detail "
               "BRIDGE_SEQ=" WS-SEQ DELIMITED BY SIZE
               " BRIDGE_ACCOUNT=" WS-ACCOUNT DELIMITED BY SPACE
               " BRIDGE_OP=" WS-OP DELIMITED BY SPACE
               " BRIDGE_AMOUNT=" WS-AMOUNT DELIMITED BY SIZE
               " BRIDGE_EVENT_ID=" WS-EVENT-ID DELIMITED BY SPACE
               INTO WS-CMD-LINE
           END-STRING
           IF WS-BRIDGE-FLAGS NOT = SPACES
               STRING WS-CMD-LINE DELIMITED BY SPACE
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
           STRING "bash /app/bin/finbulk_op.sh append-reject "
               "BRIDGE_SEQ=" WS-SEQ DELIMITED BY SIZE
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
           STRING "bash /app/bin/finbulk_op.sh append-pending-lock "
               "BRIDGE_SEQ=" WS-SEQ DELIMITED BY SIZE
               " BRIDGE_ACCOUNT=" WS-ACCOUNT DELIMITED BY SPACE
               " BRIDGE_EVENT_ID=" WS-EVENT-ID DELIMITED BY SPACE
               INTO WS-CMD-LINE
           END-STRING
           CALL "SYSTEM" USING WS-CMD-LINE
           .

       DO-SAVE-DB.
           CALL "SYSTEM" USING "bash /app/bin/finbulk_op.sh save"
           .

       DO-WRITE-OUTPUTS.
           MOVE SPACES TO WS-CMD-LINE
           STRING "bash /app/bin/finbulk_op.sh write-outputs "
               "BRIDGE_STATUS=" WS-STATUS DELIMITED BY SPACE
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
           STRING "bash /app/bin/finbulk_op.sh failed-closed "
               "BRIDGE_ERROR=" WS-ERROR-MSG DELIMITED BY SPACE
               INTO WS-CMD-LINE
           END-STRING
           CALL "SYSTEM" USING WS-CMD-LINE
           .

       DO-VALIDATE-CONTROL.
           MOVE SPACES TO WS-CMD-LINE
           STRING "bash /app/bin/finbulk_op.sh validate-control "
               "BRIDGE_INPUT=" FINBULK-INPUT-NAME DELIMITED BY SPACE
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
           STRING "bash /app/bin/finbulk_op.sh enforce-control-replay "
               "BRIDGE_INPUT_HASH=" WS-INPUT-HASH DELIMITED BY SPACE
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
           STRING "bash /app/bin/finbulk_op.sh record-control-total "
               "BRIDGE_INPUT_HASH=" WS-INPUT-HASH DELIMITED BY SPACE
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


def main() -> None:
    for name, cfg in VARIANTS.items():
        text = TEMPLATE.format(**cfg)
        cfg["path"].write_text(text, encoding="utf-8", newline="\n")
        print(f"wrote {name}: {cfg['path']}")


if __name__ == "__main__":
    main()
