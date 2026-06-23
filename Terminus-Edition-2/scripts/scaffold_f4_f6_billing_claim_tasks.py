#!/usr/bin/env python3
"""Scaffold F4 billing approval and F6 claim disbursement COBOL incident tasks."""
from __future__ import annotations

import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

F4_CBL = r'''       IDENTIFICATION DIVISION.
       PROGRAM-ID. BILLING-APPROVAL.
       ENVIRONMENT DIVISION.
       INPUT-OUTPUT SECTION.
       FILE-CONTROL.
           SELECT MANIFEST-FILE ASSIGN TO "/app/config/usage_manifest.txt"
               ORGANIZATION IS LINE SEQUENTIAL.
           SELECT MATRIX-FILE ASSIGN TO "/app/config/approval_matrix.txt"
               ORGANIZATION IS LINE SEQUENTIAL.
           SELECT MASTER-FILE ASSIGN TO "/app/config/account_master.txt"
               ORGANIZATION IS LINE SEQUENTIAL.
           SELECT LEDGER-FILE ASSIGN TO "/app/config/prior_ledger.dat"
               ORGANIZATION IS LINE SEQUENTIAL.
           SELECT USG-FILE ASSIGN TO WS-USG-PATH
               ORGANIZATION IS LINE SEQUENTIAL.
           SELECT INV-FILE ASSIGN TO "/app/out/invoice_register.dat"
               ORGANIZATION IS LINE SEQUENTIAL.
           SELECT TRACE-FILE ASSIGN TO "/app/out/approval_trace.dat"
               ORGANIZATION IS LINE SEQUENTIAL.
           SELECT SUMMARY-FILE ASSIGN TO "/app/out/billing_summary.txt"
               ORGANIZATION IS LINE SEQUENTIAL.
           SELECT CHECKPOINT-FILE ASSIGN TO "/app/out/checkpoint.dat"
               ORGANIZATION IS LINE SEQUENTIAL.
       DATA DIVISION.
       FILE SECTION.
       FD MANIFEST-FILE.
       01 MANIFEST-LINE PIC X(120).
       FD MATRIX-FILE.
       01 MATRIX-LINE PIC X(80).
       FD MASTER-FILE.
       01 MASTER-LINE PIC X(80).
       FD LEDGER-FILE.
       01 LEDGER-LINE PIC X(40).
       FD USG-FILE.
       01 USG-LINE PIC X(52).
       FD INV-FILE.
       01 INV-OUT-REC PIC X(72).
       FD TRACE-FILE.
       01 TRACE-OUT-REC PIC X(40).
       FD SUMMARY-FILE.
       01 SUMMARY-LINE PIC X(80).
       FD CHECKPOINT-FILE.
       01 WS-CKPT-REC PIC X(200).
       WORKING-STORAGE SECTION.
       COPY "usage-record".
       COPY "invoice-record".
       COPY "trace-record".
       COPY "ledger-record".
       01 WS-USG-PATH PIC X(120) VALUE SPACES.
       01 WS-EOF-MAN PIC X VALUE "N".
       01 WS-EOF-USG PIC X VALUE "N".
       01 WS-MANIFEST-COUNT PIC 9(2) VALUE 0.
       01 WS-MAN-IDX PIC 9(2) VALUE 0.
       01 WS-MAN-PATH.
          05 WS-MAN-ENTRY OCCURS 5 TIMES PIC X(120).
       01 WS-REGIONAL-CENTS PIC 9(10) VALUE 500000.
       01 WS-DUAL-CENTS PIC 9(10) VALUE 2000000.
       01 WS-CURRENT-ACCOUNT PIC X(8) VALUE SPACES.
       01 WS-ACCOUNT-TOTAL PIC S9(10) VALUE 0.
       01 WS-LAST-LINE-AMOUNT PIC S9(10) VALUE 0.
       01 WS-USAGE-COUNT PIC 9(6) VALUE 0.
       01 WS-ROW-COUNT PIC 9(6) VALUE 0.
       01 WS-BATCH-COUNT PIC 9(2) VALUE 0.
       01 WS-BATCH-IDX PIC 9(2) VALUE 0.
       01 WS-BATCH-TABLE.
          05 WS-BATCH-ENTRY OCCURS 8 TIMES PIC X(6).
       01 WS-ACCOUNT-STATUS PIC X(8) VALUE "OPEN".
       01 WS-APPROVAL-TIER PIC X(10) VALUE SPACES.
       01 WS-FINAL-STATUS PIC X(8) VALUE SPACES.
       01 WS-STAGE-TRACE PIC X(16) VALUE SPACES.
       01 WS-DUP-BATCH-FOUND PIC X VALUE "N".
       01 WS-INVOICE-COUNTER PIC 9(10) VALUE 0.
       01 WS-INVOICES-POSTED PIC 9(6) VALUE 0.
       01 WS-TOTAL-BILLED PIC S9(12) VALUE 0.
       01 WS-DUP-BLOCKED PIC 9(6) VALUE 0.
       01 WS-CHECKPOINT-COMMITS PIC 9(6) VALUE 0.
       01 WS-ABEND-AFTER PIC 9(6) VALUE 0.
       01 WS-ABEND-LIMIT PIC X(10) VALUE SPACES.
       01 WS-RESTART-ENV PIC X(4) VALUE SPACES.
       01 WS-RESTART-FLAG PIC X VALUE "N".
       01 WS-RESTART-ACTIVE PIC X VALUE "N".
       01 WS-PROCESS-RECORD PIC X VALUE "Y".
       01 WS-CURRENT-FILE-NUM PIC 9(2) VALUE 0.
       01 WS-FILE-RECORD-NUM PIC 9(6) VALUE 0.
       01 WS-CKPT-FILE-NUM PIC 9(2) VALUE 0.
       01 WS-CKPT-RECORD-NUM PIC 9(6) VALUE 0.
       01 WS-DSP PIC Z(10)9.
       PROCEDURE DIVISION.
       MAIN-PARA.
           CALL "SYSTEM" USING "mkdir -p /app/out"
           PERFORM LOAD-MATRIX
           PERFORM LOAD-MANIFEST
           IF WS-RESTART-FLAG = "Y"
               PERFORM LOAD-CHECKPOINT
               OPEN EXTEND INV-FILE
               OPEN EXTEND TRACE-FILE
           ELSE
               OPEN OUTPUT INV-FILE
               OPEN OUTPUT TRACE-FILE
           END-IF
           OPEN OUTPUT SUMMARY-FILE
           PERFORM VARYING WS-MAN-IDX FROM 1 BY 1
               UNTIL WS-MAN-IDX > WS-MANIFEST-COUNT
               MOVE WS-MAN-IDX TO WS-CURRENT-FILE-NUM
               MOVE WS-MAN-ENTRY(WS-MAN-IDX) TO WS-USG-PATH
               OPEN INPUT USG-FILE
               PERFORM PROCESS-USAGE-STREAM
               CLOSE USG-FILE
           END-PERFORM
           PERFORM FINALIZE-ACCOUNT
           PERFORM WRITE-SUMMARY
           CLOSE INV-FILE
           CLOSE TRACE-FILE
           CLOSE SUMMARY-FILE
           STOP RUN.

       READ-RUNTIME-FLAGS.
           MOVE SPACES TO WS-ABEND-LIMIT
           ACCEPT WS-ABEND-LIMIT FROM ENVIRONMENT "BILLING_ABEND_AFTER"
           IF WS-ABEND-LIMIT NOT = SPACES
               MOVE WS-ABEND-LIMIT TO WS-ABEND-AFTER
           END-IF
           MOVE SPACES TO WS-RESTART-ENV
           ACCEPT WS-RESTART-ENV FROM ENVIRONMENT "BILLING_RESTART"
           IF WS-RESTART-ENV = "1"
               MOVE "Y" TO WS-RESTART-FLAG
           END-IF.

       LOAD-MATRIX.
           OPEN INPUT MATRIX-FILE
           PERFORM UNTIL WS-EOF-MAN = "Y"
               READ MATRIX-FILE AT END MOVE "Y" TO WS-EOF-MAN
               NOT AT END
                   IF MATRIX-LINE(1:14) = "regional_cents="
                       MOVE MATRIX-LINE(15:10) TO WS-REGIONAL-CENTS
                   END-IF
                   IF MATRIX-LINE(1:10) = "dual_cents="
                       MOVE MATRIX-LINE(11:10) TO WS-DUAL-CENTS
                   END-IF
               END-READ
           END-PERFORM
           CLOSE MATRIX-FILE
           MOVE "N" TO WS-EOF-MAN.

       LOAD-MANIFEST.
           OPEN INPUT MANIFEST-FILE
           PERFORM UNTIL WS-EOF-MAN = "Y"
               READ MANIFEST-FILE AT END MOVE "Y" TO WS-EOF-MAN
               NOT AT END
                   IF MANIFEST-LINE(1:1) NOT = SPACES
                       ADD 1 TO WS-MANIFEST-COUNT
                       MOVE MANIFEST-LINE(4:117) TO WS-MAN-ENTRY(WS-MANIFEST-COUNT)
                   END-IF
               END-READ
           END-PERFORM
           CLOSE MANIFEST-FILE
           MOVE "N" TO WS-EOF-MAN
           PERFORM READ-RUNTIME-FLAGS.

       PROCESS-USAGE-STREAM.
           MOVE "N" TO WS-EOF-USG
           PERFORM UNTIL WS-EOF-USG = "Y"
               READ USG-FILE AT END MOVE "Y" TO WS-EOF-USG
               NOT AT END
                   ADD 1 TO WS-FILE-RECORD-NUM
                   MOVE "Y" TO WS-PROCESS-RECORD
                   IF WS-RESTART-ACTIVE = "Y"
                       IF WS-CURRENT-FILE-NUM < WS-CKPT-FILE-NUM
                           MOVE "N" TO WS-PROCESS-RECORD
                       END-IF
                       IF WS-CURRENT-FILE-NUM = WS-CKPT-FILE-NUM
                           AND WS-FILE-RECORD-NUM <= WS-CKPT-RECORD-NUM
                           MOVE "N" TO WS-PROCESS-RECORD
                       END-IF
                       IF WS-PROCESS-RECORD = "Y"
                           MOVE "N" TO WS-RESTART-ACTIVE
                       END-IF
                   END-IF
                   IF WS-PROCESS-RECORD = "Y"
                       PERFORM HANDLE-USAGE-LINE
                   END-IF
               END-READ
           END-PERFORM.

       HANDLE-USAGE-LINE.
           MOVE USG-LINE TO USG-IN-REC
           IF USG-TYPE NOT = "U"
               GO TO HANDLE-DONE
           END-IF
           IF WS-CURRENT-ACCOUNT NOT = SPACES
               AND USG-ACCOUNT NOT = WS-CURRENT-ACCOUNT
               PERFORM FINALIZE-ACCOUNT
           END-IF
           IF WS-CURRENT-ACCOUNT = SPACES
               MOVE USG-ACCOUNT TO WS-CURRENT-ACCOUNT
           END-IF
           ADD USG-AMOUNT TO WS-ACCOUNT-TOTAL
           ADD 1 TO WS-USAGE-COUNT
           ADD 1 TO WS-ROW-COUNT
           MOVE USG-AMOUNT TO WS-LAST-LINE-AMOUNT
           PERFORM TRACK-BATCH
           IF WS-RESTART-ACTIVE = "Y"
               PERFORM FINALIZE-ACCOUNT
           END-IF
           IF WS-ABEND-AFTER > 0 AND WS-ROW-COUNT >= WS-ABEND-AFTER
               PERFORM WRITE-CHECKPOINT
               STOP RUN 99
           END-IF
           .

       HANDLE-DONE.
           EXIT.

       TRACK-BATCH.
           PERFORM VARYING WS-BATCH-IDX FROM 1 BY 1 UNTIL WS-BATCH-IDX > WS-BATCH-COUNT
               IF WS-BATCH-ENTRY(WS-BATCH-IDX) = USG-BATCH
                   GO TO TRACK-DONE
               END-IF
           END-PERFORM
           IF WS-BATCH-COUNT < 8
               ADD 1 TO WS-BATCH-COUNT
               MOVE USG-BATCH TO WS-BATCH-ENTRY(WS-BATCH-COUNT)
           END-IF
           .

       TRACK-DONE.
           EXIT.

       FINALIZE-ACCOUNT.
           IF WS-USAGE-COUNT = 0
               GO TO FINALIZE-DONE
           END-IF
           PERFORM LOOKUP-ACCOUNT-STATUS
           IF WS-ACCOUNT-STATUS = "CLOSED"
               MOVE "HOLD" TO WS-FINAL-STATUS
               MOVE "CLOSED" TO WS-APPROVAL-TIER
               MOVE "CLOSED" TO WS-STAGE-TRACE
               GO TO FINALIZE-WRITE
           END-IF
           PERFORM CHECK-PRIOR-LEDGER
           IF WS-DUP-BATCH-FOUND = "Y"
               ADD 1 TO WS-DUP-BLOCKED
               MOVE "DUPBATCH" TO WS-FINAL-STATUS
               GO TO FINALIZE-RESET
           END-IF
           PERFORM DETERMINE-APPROVAL-TIER
           PERFORM RUN-APPROVAL-CHAIN
           .

       FINALIZE-WRITE.
           IF WS-FINAL-STATUS = "APPROVED"
               PERFORM WRITE-INVOICE
           ELSE
               PERFORM FINALIZE-RESET
           END-IF
           .

       FINALIZE-RESET.
           MOVE SPACES TO WS-CURRENT-ACCOUNT
           MOVE ZERO TO WS-ACCOUNT-TOTAL
           MOVE ZERO TO WS-LAST-LINE-AMOUNT
           MOVE ZERO TO WS-USAGE-COUNT
           MOVE ZERO TO WS-BATCH-COUNT
           MOVE SPACES TO WS-APPROVAL-TIER
           MOVE SPACES TO WS-FINAL-STATUS
           MOVE SPACES TO WS-STAGE-TRACE
           MOVE "N" TO WS-DUP-BATCH-FOUND
           .

       FINALIZE-DONE.
           EXIT.

       LOOKUP-ACCOUNT-STATUS.
           MOVE "OPEN" TO WS-ACCOUNT-STATUS
           OPEN INPUT MASTER-FILE
           PERFORM UNTIL WS-EOF-MAN = "Y"
               READ MASTER-FILE AT END MOVE "Y" TO WS-EOF-MAN
               NOT AT END
                   IF MASTER-LINE(1:8) = WS-CURRENT-ACCOUNT
                       IF MASTER-LINE(10:6) = "CLOSED"
                           MOVE "CLOSED" TO WS-ACCOUNT-STATUS
                       END-IF
                   END-IF
               END-READ
           END-PERFORM
           CLOSE MASTER-FILE
           MOVE "N" TO WS-EOF-MAN.

       DETERMINE-APPROVAL-TIER.
           MOVE WS-LAST-LINE-AMOUNT TO WS-TIER-AMOUNT
           IF WS-TIER-AMOUNT < 0
               MOVE "CREDITREV" TO WS-APPROVAL-TIER
               MOVE "HOLD" TO WS-FINAL-STATUS
               MOVE "CREDIT" TO WS-STAGE-TRACE
               GO TO TIER-DONE
           END-IF
           IF WS-TIER-AMOUNT < WS-REGIONAL-CENTS
               MOVE "AUTO" TO WS-APPROVAL-TIER
           ELSE
               IF WS-TIER-AMOUNT < WS-DUAL-CENTS
                   MOVE "REGIONAL" TO WS-APPROVAL-TIER
               ELSE
                   MOVE "DUAL" TO WS-APPROVAL-TIER
               END-IF
           END-IF
           .

       TIER-DONE.
           EXIT.

       CHECK-PRIOR-LEDGER.
           MOVE "N" TO WS-DUP-BATCH-FOUND.

       RUN-APPROVAL-CHAIN.
           IF WS-FINAL-STATUS = "HOLD"
               GO TO CHAIN-DONE
           END-IF
           IF WS-APPROVAL-TIER = "AUTO"
               MOVE "AUTO" TO WS-STAGE-TRACE
               MOVE "APPROVED" TO WS-FINAL-STATUS
               GO TO CHAIN-DONE
           END-IF
           IF WS-APPROVAL-TIER = "REGIONAL"
               PERFORM WRITE-TRACE-REGIONAL
               MOVE "REGIONAL" TO WS-STAGE-TRACE
               MOVE "APPROVED" TO WS-FINAL-STATUS
               GO TO CHAIN-DONE
           END-IF
           IF WS-APPROVAL-TIER = "DUAL"
               PERFORM WRITE-TRACE-REGIONAL
               MOVE "REGIONAL" TO WS-STAGE-TRACE
               MOVE "APPROVED" TO WS-FINAL-STATUS
               GO TO CHAIN-DONE
           END-IF
           .

       CHAIN-DONE.
           GO TO FINALIZE-WRITE.

       WRITE-TRACE-REGIONAL.
           MOVE "T" TO TR-TYPE
           MOVE WS-CURRENT-ACCOUNT TO TR-ACCOUNT
           MOVE "REGIONAL" TO TR-STAGE
           MOVE "PASS" TO TR-RESULT
           MOVE SPACES TO TR-FILLER
           WRITE TRACE-OUT-REC FROM TR-OUT-REC
           .

       WRITE-TRACE-FINANCE.
           MOVE "T" TO TR-TYPE
           MOVE WS-CURRENT-ACCOUNT TO TR-ACCOUNT
           MOVE "FINANCE" TO TR-STAGE
           MOVE "PASS" TO TR-RESULT
           MOVE SPACES TO TR-FILLER
           WRITE TRACE-OUT-REC FROM TR-OUT-REC
           .

       WRITE-INVOICE.
           ADD 1 TO WS-INVOICE-COUNTER
           ADD 1 TO WS-INVOICES-POSTED
           ADD WS-ACCOUNT-TOTAL TO WS-TOTAL-BILLED
           MOVE "I" TO INV-TYPE
           MOVE WS-CURRENT-ACCOUNT TO INV-ACCOUNT
           MOVE WS-INVOICE-COUNTER TO INV-NUMBER
           MOVE WS-ACCOUNT-TOTAL TO INV-TOTAL
           MOVE WS-APPROVAL-TIER TO INV-TIER
           MOVE WS-STAGE-TRACE TO INV-STAGES
           MOVE WS-FINAL-STATUS TO INV-STATUS
           MOVE SPACES TO INV-FILLER
           MOVE INV-OUT-REC-DATA TO INV-OUT-BUF
           WRITE INV-OUT-REC FROM INV-OUT-BUF
           PERFORM FINALIZE-RESET.

       WRITE-CHECKPOINT.
           OPEN OUTPUT CHECKPOINT-FILE
           STRING "file_num=" DELIMITED BY SIZE WS-CURRENT-FILE-NUM DELIMITED BY SIZE
               "|record_num=" DELIMITED BY SIZE WS-FILE-RECORD-NUM DELIMITED BY SIZE
               "|account=" DELIMITED BY SIZE WS-CURRENT-ACCOUNT DELIMITED BY SIZE
               "|acct_total=" DELIMITED BY SIZE WS-ACCOUNT-TOTAL DELIMITED BY SIZE
               "|usage_count=" DELIMITED BY SIZE WS-USAGE-COUNT DELIMITED BY SIZE
               "|invoice_counter=" DELIMITED BY SIZE WS-INVOICE-COUNTER DELIMITED BY SIZE
               "|row_count=" DELIMITED BY SIZE WS-ROW-COUNT DELIMITED BY SIZE
               INTO WS-CKPT-REC END-STRING
           WRITE WS-CKPT-REC
           CLOSE CHECKPOINT-FILE
           ADD 1 TO WS-CHECKPOINT-COMMITS.

       LOAD-CHECKPOINT.
           OPEN INPUT CHECKPOINT-FILE
           READ CHECKPOINT-FILE
               AT END MOVE "N" TO WS-RESTART-FLAG
               NOT AT END
                   PERFORM PARSE-CHECKPOINT-LINE
                   MOVE "Y" TO WS-RESTART-ACTIVE
           END-READ
           CLOSE CHECKPOINT-FILE.

       PARSE-CHECKPOINT-LINE.
           *> simplified parse via fixed substrings after known keys
           MOVE WS-CKPT-REC(9:2) TO WS-CKPT-FILE-NUM
           MOVE WS-CKPT-REC(24:6) TO WS-CKPT-RECORD-NUM
           MOVE WS-CKPT-REC(40:8) TO WS-CURRENT-ACCOUNT
           MOVE WS-CKPT-REC(58:10) TO WS-ACCOUNT-TOTAL
           MOVE WS-CKPT-REC(78:6) TO WS-USAGE-COUNT
           MOVE WS-CKPT-REC(101:10) TO WS-INVOICE-COUNTER
           MOVE WS-CKPT-REC(120:6) TO WS-ROW-COUNT
           .

       WRITE-SUMMARY.
           MOVE WS-INVOICES-POSTED TO WS-DSP
           MOVE SPACES TO SUMMARY-LINE
           STRING "invoices_posted=" DELIMITED BY SIZE
               FUNCTION TRIM(WS-DSP LEADING) DELIMITED BY SIZE INTO SUMMARY-LINE END-STRING
           WRITE SUMMARY-LINE
           MOVE WS-TOTAL-BILLED TO WS-DSP
           MOVE SPACES TO SUMMARY-LINE
           STRING "total_billed_cents=" DELIMITED BY SIZE
               FUNCTION TRIM(WS-DSP LEADING) DELIMITED BY SIZE INTO SUMMARY-LINE END-STRING
           WRITE SUMMARY-LINE
           MOVE WS-ROW-COUNT TO WS-DSP
           MOVE SPACES TO SUMMARY-LINE
           STRING "usage_rows=" DELIMITED BY SIZE
               FUNCTION TRIM(WS-DSP LEADING) DELIMITED BY SIZE INTO SUMMARY-LINE END-STRING
           WRITE SUMMARY-LINE
           MOVE WS-DUP-BLOCKED TO WS-DSP
           MOVE SPACES TO SUMMARY-LINE
           STRING "duplicate_batches_blocked=" DELIMITED BY SIZE
               FUNCTION TRIM(WS-DSP LEADING) DELIMITED BY SIZE INTO SUMMARY-LINE END-STRING
           WRITE SUMMARY-LINE
           MOVE WS-CHECKPOINT-COMMITS TO WS-DSP
           MOVE SPACES TO SUMMARY-LINE
           STRING "checkpoint_commits=" DELIMITED BY SIZE
               FUNCTION TRIM(WS-DSP LEADING) DELIMITED BY SIZE INTO SUMMARY-LINE END-STRING
           WRITE SUMMARY-LINE
           .
'''

USAGE_CPY = """      * Usage charge input (52 bytes)
       01 USG-IN-REC.
          05 USG-TYPE           PIC X.
          05 USG-ACCOUNT        PIC X(8).
          05 USG-BATCH          PIC X(6).
          05 USG-SEQ            PIC X(4).
          05 USG-AMOUNT         PIC S9(10).
          05 USG-SERVICE        PIC X(4).
          05 USG-FILLER         PIC X(19).
       01 WS-TIER-AMOUNT        PIC S9(10).
"""

INV_CPY = """      * Invoice output (72 bytes)
       01 INV-OUT-REC-DATA.
          05 INV-TYPE           PIC X.
          05 INV-ACCOUNT        PIC X(8).
          05 INV-NUMBER         PIC 9(10).
          05 INV-TOTAL          PIC S9(10).
          05 INV-TIER           PIC X(10).
          05 INV-STAGES         PIC X(16).
          05 INV-STATUS         PIC X(8).
          05 INV-FILLER         PIC X(17).
       01 INV-OUT-BUF REDEFINES INV-OUT-REC-DATA PIC X(72).
"""

TRACE_CPY = """      * Approval trace (40 bytes)
       01 TR-OUT-REC.
          05 TR-TYPE            PIC X.
          05 TR-ACCOUNT         PIC X(8).
          05 TR-STAGE           PIC X(8).
          05 TR-RESULT          PIC X(8).
          05 TR-FILLER          PIC X(15).
"""

LEDGER_CPY = """      * Prior billed batch ledger (40 bytes)
       01 LED-IN-REC.
          05 LED-TYPE           PIC X.
          05 LED-ACCOUNT        PIC X(8).
          05 LED-BATCH          PIC X(6).
          05 LED-INVOICE        PIC X(10).
          05 LED-AMOUNT         PIC 9(10).
          05 LED-FILLER         PIC X(5).
"""


def write_lf(path: Path, content: str) -> None:
    path.write_text(content.replace("\r\n", "\n"), encoding="utf-8", newline="\n")


def scaffold_f4(task_dir: Path) -> None:
    env = task_dir / "environment"
    src = env / "src"
    src.mkdir(parents=True, exist_ok=True)
    (src / "billing_approval.cbl").write_text(F4_CBL, encoding="utf-8")
    if (src / "stmt_merge.cbl").exists():
        (src / "stmt_merge.cbl").unlink()

    cb = env / "copybooks"
    write_lf(cb / "usage-record.cpy", USAGE_CPY)
    write_lf(cb / "invoice-record.cpy", INV_CPY)
    write_lf(cb / "trace-record.cpy", TRACE_CPY)
    write_lf(cb / "ledger-record.cpy", LEDGER_CPY)
    for old in ("statement-record.cpy", "control-total-record.cpy"):
        p = cb / old
        if p.exists():
            p.unlink()

    write_lf(
        env / "scripts" / "compile.sh",
        """#!/usr/bin/env bash
set -euo pipefail
mkdir -p /app/build
cobc -x -free -I /app/copybooks -o /app/build/batch /app/src/billing_approval.cbl
""",
    )
    write_lf(
        env / "scripts" / "clean_outputs.sh",
        """#!/usr/bin/env bash
set -euo pipefail
rm -f /app/out/invoice_register.dat /app/out/approval_trace.dat /app/out/billing_summary.txt /app/out/checkpoint.dat
""",
    )
    write_lf(
        env / "scripts" / "run_batch.sh",
        """#!/usr/bin/env bash
set -euo pipefail
/app/scripts/compile.sh
exec /app/build/batch
""",
    )

    cfg = env / "config"
    write_lf(cfg / "approval_matrix.txt", "regional_cents=500000\ndual_cents=2000000\n")
    write_lf(cfg / "usage_manifest.txt", "01 /app/data/run01.usg\n")
    write_lf(cfg / "account_master.txt", "ACCT9001 CLOSED\n")
    write_lf(cfg / "prior_ledger.dat", "PACCT1001BATCH1INV00000010000050000\n")

    write_lf(
        task_dir / "task.toml",
        """version = "2.0"

[metadata]
author_name = "anonymous"
author_email = "anonymous@example.com"
difficulty = "hard"
category = "debugging"
subcategories = []
number_of_milestones = 4
codebase_size = "small"
languages = ["cobol", "bash"]
tags = ["cobol", "gnucobol", "batch-processing", "billing", "approval", "checkpoint", "debugging"]
expert_time_estimate_min = 150
junior_time_estimate_min = 300

[environment]
allow_internet = false
build_timeout_sec = 900.0
cpus = 2
memory_mb = 4096
storage_mb = 10240
workdir = "/app"

[[steps]]
name = "milestone_1"
[steps.agent]
timeout_sec = 1800.0
[steps.verifier]
timeout_sec = 900.0

[[steps]]
name = "milestone_2"
[steps.agent]
timeout_sec = 1800.0
[steps.verifier]
timeout_sec = 900.0

[[steps]]
name = "milestone_3"
[steps.agent]
timeout_sec = 1800.0
[steps.verifier]
timeout_sec = 900.0

[[steps]]
name = "milestone_4"
[steps.agent]
timeout_sec = 1800.0
[steps.verifier]
timeout_sec = 900.0
""",
    )

    helpers = '''"""Shared helpers for enterprise billing approval tests."""
import os
import subprocess
from pathlib import Path

APP = Path("/app")
MANIFEST = APP / "config" / "usage_manifest.txt"
INV = APP / "out" / "invoice_register.dat"
TRACE = APP / "out" / "approval_trace.dat"
SUMMARY = APP / "out" / "billing_summary.txt"
CHECKPOINT = APP / "out" / "checkpoint.dat"
PRIOR = APP / "config" / "prior_ledger.dat"
COMPILE_TIMEOUT = 45
RUN_TIMEOUT = 15


def fmt_usage(account: str, batch: str, seq: str, amount: int, service: str = "SVC1") -> str:
    line = f"U{account}{batch}{seq}{amount:010d}{service}"
    assert len(line) <= 52, line
    return line.ljust(52)


def parse_invoices(text: str) -> list[dict]:
    rows = []
    for raw in text.splitlines():
        line = raw.rstrip("\n")
        if not line or line[0] != "I":
            continue
        rows.append(
            {
                "account_id": line[1:9],
                "invoice_no": int(line[9:19]),
                "total_cents": int(line[19:29]),
                "approval_tier": line[29:39].strip(),
                "stages": line[39:55].strip(),
                "status": line[55:63].strip(),
            }
        )
    return rows


def parse_trace(text: str) -> list[dict]:
    rows = []
    for raw in text.splitlines():
        line = raw.rstrip("\n")
        if not line or line[0] != "T":
            continue
        rows.append(
            {
                "account_id": line[1:9],
                "stage": line[9:17].strip(),
                "result": line[17:25].strip(),
            }
        )
    return rows


def parse_summary(text: str) -> dict[str, int]:
    out: dict[str, int] = {}
    for raw in text.splitlines():
        if "=" not in raw:
            continue
        key, value = raw.split("=", 1)
        out[key.strip()] = int(value.strip())
    return out


def compile_program() -> None:
    subprocess.run(["/app/scripts/compile.sh"], check=True, cwd=APP, timeout=COMPILE_TIMEOUT)
    assert (APP / "build" / "batch").read_bytes().startswith(b"\x7fELF")


def write_manifest(paths: list[str]) -> None:
    lines = [f"{idx:02d} {path}" for idx, path in enumerate(paths, start=1)]
    MANIFEST.write_text("\n".join(lines) + "\n")


def write_usage(path: Path, rows: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    normalized = []
    for row in rows:
        if len(row) < 52:
            row = row.ljust(52)
        assert len(row) == 52, f"bad row length {len(row)}: {row!r}"
        normalized.append(row)
    path.write_text("\n".join(normalized) + "\n")


def write_prior(rows: list[str]) -> None:
    PRIOR.write_text("\n".join(rows) + "\n")


def clean_outputs() -> None:
    subprocess.run(["/app/scripts/clean_outputs.sh"], check=True, cwd=APP, timeout=10)


def run_batch(env: dict | None = None) -> subprocess.CompletedProcess:
    merged = os.environ.copy()
    if env:
        merged.update(env)
    return subprocess.run(
        ["/app/build/batch"],
        check=False,
        cwd=APP,
        timeout=RUN_TIMEOUT,
        env=merged,
        capture_output=True,
        text=True,
    )


def run_full(env: dict | None = None) -> tuple[list[dict], list[dict], dict[str, int]]:
    clean_outputs()
    compile_program()
    proc = run_batch(env)
    assert proc.returncode == 0, proc.stderr or proc.stdout
    invoices = parse_invoices(INV.read_text())
    trace = parse_trace(TRACE.read_text())
    summary = parse_summary(SUMMARY.read_text())
    return invoices, trace, summary
'''

    test_m1 = '''"""Milestone 1 — approval tier must use account billing total."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from billing_test_helpers import APP, fmt_usage, run_full, write_manifest, write_usage


class TestMilestone1:
    def test_dual_tier_requires_aggregate_not_last_line(self):
        """Small lines summing above dual threshold must route to DUAL approval."""
        run1 = APP / "data" / "run01.usg"
        write_manifest(["/app/data/run01.usg"])
        write_usage(
            run1,
            [
                fmt_usage("ACCT1001", "BATCH1", "0001", 800000),
                fmt_usage("ACCT1001", "BATCH1", "0002", 800000),
                fmt_usage("ACCT1001", "BATCH1", "0003", 800000),
            ],
        )
        invoices, trace, summary = run_full()
        assert summary["invoices_posted"] == 1
        assert invoices[0]["total_cents"] == 2400000
        assert invoices[0]["approval_tier"] == "DUAL"
        assert summary["usage_rows"] == 3

    def test_regional_tier_from_account_total(self):
        run1 = APP / "data" / "run01.usg"
        write_manifest(["/app/data/run01.usg"])
        write_usage(
            run1,
            [
                fmt_usage("ACCT2001", "BATCH2", "0001", 100000),
                fmt_usage("ACCT2001", "BATCH2", "0002", 450000),
            ],
        )
        invoices, _, summary = run_full()
        assert invoices[0]["approval_tier"] == "REGIONAL"
        assert invoices[0]["total_cents"] == 550000
        assert summary["invoices_posted"] == 1

    def test_auto_tier_when_aggregate_below_regional(self):
        run1 = APP / "data" / "run01.usg"
        write_manifest(["/app/data/run01.usg"])
        write_usage(
            run1,
            [
                fmt_usage("ACCT3001", "BATCH3", "0001", 200000),
                fmt_usage("ACCT3001", "BATCH3", "0002", 200000),
            ],
        )
        invoices, _, _ = run_full()
        assert invoices[0]["approval_tier"] == "AUTO"
        assert invoices[0]["stages"] == "AUTO"

    def test_summary_keys_present(self):
        run1 = APP / "data" / "run01.usg"
        write_manifest(["/app/data/run01.usg"])
        write_usage(run1, [fmt_usage("ACCT4001", "BATCH4", "0001", 10000)])
        _, _, summary = run_full()
        assert set(summary.keys()) == {
            "invoices_posted",
            "total_billed_cents",
            "usage_rows",
            "duplicate_batches_blocked",
            "checkpoint_commits",
        }
'''

    test_m2 = '''"""Milestone 2 — prior-run ledger duplicate batch protection."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from billing_test_helpers import APP, fmt_usage, run_full, write_manifest, write_prior, write_usage


class TestMilestone2:
    def test_prior_ledger_blocks_duplicate_batch(self):
        run1 = APP / "data" / "run01.usg"
        write_prior(["PACCT1001BATCH1INV000000010000050000"])
        write_manifest(["/app/data/run01.usg"])
        write_usage(run1, [fmt_usage("ACCT1001", "BATCH1", "0001", 50000)])
        invoices, _, summary = run_full()
        assert summary["invoices_posted"] == 0
        assert summary["duplicate_batches_blocked"] == 1
        assert invoices == []

    def test_new_batch_still_posts(self):
        run1 = APP / "data" / "run01.usg"
        write_prior(["PACCT1001BATCH1INV000000010000050000"])
        write_manifest(["/app/data/run01.usg"])
        write_usage(run1, [fmt_usage("ACCT1001", "BATCH2", "0001", 120000)])
        invoices, _, summary = run_full()
        assert summary["invoices_posted"] == 1
        assert summary["duplicate_batches_blocked"] == 0
        assert invoices[0]["total_cents"] == 120000

    def test_duplicate_only_when_account_and_batch_match(self):
        run1 = APP / "data" / "run01.usg"
        write_prior(["PACCT1001BATCH1INV000000010000050000"])
        write_manifest(["/app/data/run01.usg"])
        write_usage(run1, [fmt_usage("ACCT2001", "BATCH1", "0001", 90000)])
        invoices, _, summary = run_full()
        assert summary["invoices_posted"] == 1
        assert summary["duplicate_batches_blocked"] == 0
'''

    test_m3 = '''"""Milestone 3 — dual approval requires regional and finance stages."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from billing_test_helpers import APP, fmt_usage, run_full, write_manifest, write_usage


class TestMilestone3:
    def test_dual_posts_finance_trace(self):
        run1 = APP / "data" / "run01.usg"
        write_manifest(["/app/data/run01.usg"])
        write_usage(
            run1,
            [
                fmt_usage("ACCT1001", "BATCH1", "0001", 1000000),
                fmt_usage("ACCT1001", "BATCH1", "0002", 1100000),
            ],
        )
        invoices, trace, summary = run_full()
        assert invoices[0]["approval_tier"] == "DUAL"
        stages = [t["stage"] for t in trace if t["account_id"] == "ACCT1001"]
        assert stages == ["REGIONAL", "FINANCE"]
        assert invoices[0]["stages"] == "REGIONAL+FINANCE"
        assert summary["invoices_posted"] == 1

    def test_regional_single_stage_only(self):
        run1 = APP / "data" / "run01.usg"
        write_manifest(["/app/data/run01.usg"])
        write_usage(run1, [fmt_usage("ACCT2001", "BATCH2", "0001", 600000)])
        invoices, trace, _ = run_full()
        assert invoices[0]["approval_tier"] == "REGIONAL"
        assert [t["stage"] for t in trace] == ["REGIONAL"]
'''

    test_m4 = '''"""Milestone 4 — checkpoint restart without partial invoices."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from billing_test_helpers import (  # noqa: E402
    APP,
    CHECKPOINT,
    INV,
    SUMMARY,
    compile_program,
    fmt_usage,
    parse_invoices,
    parse_summary,
    run_batch,
    run_full,
    write_manifest,
    write_usage,
)


def run_abend_restart(rows: list[str], abend_after: int):
    run1 = APP / "data" / "run01.usg"
    write_manifest(["/app/data/run01.usg"])
    write_usage(run1, rows)
    _, _, summary_clean = run_full()
    invoices_clean = parse_invoices(INV.read_text())

    from billing_test_helpers import clean_outputs

    clean_outputs()
    compile_program()
    abend = run_batch({"BILLING_ABEND_AFTER": str(abend_after)})
    assert abend.returncode == 99, abend.stderr or abend.stdout
    assert CHECKPOINT.exists()

    clean_outputs()
    compile_program()
    resumed = run_batch({"BILLING_RESTART": "1"})
    assert resumed.returncode == 0, resumed.stderr or resumed.stdout
    invoices_final = parse_invoices(INV.read_text())
    summary_final = parse_summary(SUMMARY.read_text())
    assert summary_final == summary_clean
    assert invoices_final == invoices_clean
    return invoices_clean, summary_clean


class TestMilestone4:
    def test_restart_matches_clean_run(self):
        rows = [
            fmt_usage("ACCT1001", "BATCH1", "0001", 100000),
            fmt_usage("ACCT1001", "BATCH1", "0002", 200000),
            fmt_usage("ACCT1001", "BATCH1", "0003", 300000),
        ]
        invoices, summary = run_abend_restart(rows, abend_after=2)
        assert summary["invoices_posted"] == 1
        assert invoices[0]["total_cents"] == 600000

    def test_restart_mid_account_no_partial_invoice(self):
        rows = [
            fmt_usage("ACCT2001", "BATCH2", "0001", 400000),
            fmt_usage("ACCT2001", "BATCH2", "0002", 100000),
            fmt_usage("ACCT2001", "BATCH2", "0003", 50000),
        ]
        run_abend_restart(rows, abend_after=2)
        invoices = parse_invoices(INV.read_text())
        assert len(invoices) == 1
        assert invoices[0]["total_cents"] == 550000
'''

    solve1 = '''#!/usr/bin/env bash
set -euo pipefail
cd /app
python3 <<'PY'
from pathlib import Path
path = Path("/app/src/billing_approval.cbl")
text = path.read_text()
old = "           MOVE WS-LAST-LINE-AMOUNT TO WS-TIER-AMOUNT"
new = "           MOVE WS-ACCOUNT-TOTAL TO WS-TIER-AMOUNT"
if old not in text:
    raise SystemExit("milestone 1 patch anchor missing")
path.write_text(text.replace(old, new, 1))
PY
/app/scripts/run_batch.sh
test -s /app/out/invoice_register.dat
'''

    solve2 = '''#!/usr/bin/env bash
set -euo pipefail
cd /app
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STEPS_ROOT="$(dirname "$(dirname "$SCRIPT_DIR")")"
if ! grep -q "MOVE WS-ACCOUNT-TOTAL TO WS-TIER-AMOUNT" /app/src/billing_approval.cbl; then
  bash "$STEPS_ROOT/milestone_1/solution/solve1.sh"
fi
python3 <<'PY'
from pathlib import Path
path = Path("/app/src/billing_approval.cbl")
text = path.read_text()
old = """       CHECK-PRIOR-LEDGER.
           MOVE "N" TO WS-DUP-BATCH-FOUND."""
new = """       CHECK-PRIOR-LEDGER.
           MOVE "N" TO WS-DUP-BATCH-FOUND
           OPEN INPUT LEDGER-FILE
           PERFORM UNTIL WS-EOF-MAN = "Y"
               READ LEDGER-FILE AT END MOVE "Y" TO WS-EOF-MAN
               NOT AT END
                   MOVE LEDGER-LINE TO LED-IN-REC
                   IF LED-TYPE = "P"
                       AND LED-ACCOUNT = WS-CURRENT-ACCOUNT
                       PERFORM VARYING WS-BATCH-IDX FROM 1 BY 1
                           UNTIL WS-BATCH-IDX > WS-BATCH-COUNT
                           IF LED-BATCH = WS-BATCH-ENTRY(WS-BATCH-IDX)
                               MOVE "Y" TO WS-DUP-BATCH-FOUND
                           END-IF
                       END-PERFORM
                   END-IF
               END-READ
           END-PERFORM
           CLOSE LEDGER-FILE
           MOVE "N" TO WS-EOF-MAN."""
if old not in text:
    raise SystemExit("milestone 2 patch anchor missing")
path.write_text(text.replace(old, new, 1))
PY
/app/scripts/run_batch.sh
'''

    solve3 = '''#!/usr/bin/env bash
set -euo pipefail
cd /app
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STEPS_ROOT="$(dirname "$(dirname "$SCRIPT_DIR")")"
if ! grep -q "OPEN INPUT LEDGER-FILE" /app/src/billing_approval.cbl; then
  bash "$STEPS_ROOT/milestone_2/solution/solve2.sh"
fi
python3 <<'PY'
from pathlib import Path
path = Path("/app/src/billing_approval.cbl")
text = path.read_text()
old = """           IF WS-APPROVAL-TIER = "DUAL"
               PERFORM WRITE-TRACE-REGIONAL
               MOVE "REGIONAL" TO WS-STAGE-TRACE
               MOVE "APPROVED" TO WS-FINAL-STATUS
               GO TO CHAIN-DONE
           END-IF"""
new = """           IF WS-APPROVAL-TIER = "DUAL"
               PERFORM WRITE-TRACE-REGIONAL
               PERFORM WRITE-TRACE-FINANCE
               MOVE "REGIONAL+FIN" TO WS-STAGE-TRACE
               MOVE "APPROVED" TO WS-FINAL-STATUS
               GO TO CHAIN-DONE
           END-IF"""
if old not in text:
    raise SystemExit("milestone 3 patch anchor missing")
path.write_text(text.replace(old, new, 1))
# normalize stage label for tests
text = path.read_text()
text = text.replace('MOVE "REGIONAL+FIN" TO WS-STAGE-TRACE', 'MOVE "REGIONAL+FINANCE" TO WS-STAGE-TRACE', 1)
path.write_text(text)
PY
/app/scripts/run_batch.sh
'''

    solve4 = '''#!/usr/bin/env bash
set -euo pipefail
cd /app
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STEPS_ROOT="$(dirname "$(dirname "$SCRIPT_DIR")")"
if ! grep -q "WRITE-TRACE-FINANCE" /app/src/billing_approval.cbl; then
  bash "$STEPS_ROOT/milestone_3/solution/solve3.sh"
fi
python3 <<'PY'
from pathlib import Path
path = Path("/app/src/billing_approval.cbl")
text = path.read_text()
old = """           IF WS-RESTART-ACTIVE = "Y"
               PERFORM FINALIZE-ACCOUNT
           END-IF"""
if old not in text:
    raise SystemExit("milestone 4 patch anchor missing")
text = text.replace(old, "", 1)
path.write_text(text)
PY
/app/scripts/run_batch.sh
'''

    for ms, test_py, solve_sh, solve_n in [
        (1, test_m1, solve1, "solve1.sh"),
        (2, test_m2, solve2, "solve2.sh"),
        (3, test_m3, solve3, "solve3.sh"),
        (4, test_m4, solve4, "solve4.sh"),
    ]:
        ms_dir = task_dir / "steps" / f"milestone_{ms}"
        tests = ms_dir / "tests"
        write_lf(tests / "billing_test_helpers.py", helpers)
        if (tests / "merge_test_helpers.py").exists():
            (tests / "merge_test_helpers.py").unlink()
        write_lf(tests / f"test_m{ms}.py", test_py)
        sol = ms_dir / "solution"
        write_lf(sol / solve_n, solve_sh)
        write_lf(sol / "solve.sh", f'#!/usr/bin/env bash\nset -euo pipefail\nexec bash "$(dirname "$0")/{solve_n}"\n')

    print(f"Scaffolded F4 at {task_dir}")


def main() -> None:
    f4 = ROOT / "cobol-enterprise-billing-approval-cycle"
    if not f4.exists():
        shutil.copytree(ROOT / "cobol-statement-merge-control-totals", f4)
    scaffold_f4(f4)


if __name__ == "__main__":
    main()
