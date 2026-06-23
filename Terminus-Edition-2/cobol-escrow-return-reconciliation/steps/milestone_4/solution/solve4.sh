#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd /app

python3 <<'PY'
from pathlib import Path

path = Path("/app/src/wire_returns.cbl")
text = path.read_text()

if 'SELECT JOB-FILE ASSIGN TO "/app/config/job.properties"' not in text:
    text = text.replace(
        '           SELECT REPORT-FILE ASSIGN TO "/app/out/wire_return_report.csv"\n               ORGANIZATION IS LINE SEQUENTIAL.\n           SELECT SUMMARY-FILE ASSIGN TO "/app/out/wire_return_summary.txt"\n               ORGANIZATION IS LINE SEQUENTIAL.',
        '           SELECT REPORT-FILE ASSIGN TO "/app/out/wire_return_report.csv"\n               ORGANIZATION IS LINE SEQUENTIAL.\n           SELECT SUMMARY-FILE ASSIGN TO "/app/out/wire_return_summary.txt"\n               ORGANIZATION IS LINE SEQUENTIAL.\n           SELECT JOB-FILE ASSIGN TO "/app/config/job.properties"\n               ORGANIZATION IS LINE SEQUENTIAL.',
    )

if "FD JOB-FILE." not in text:
    text = text.replace(
        '       FD SUMMARY-FILE.\n       01 SUMMARY-REC PIC X(80).',
        '       FD SUMMARY-FILE.\n       01 SUMMARY-REC PIC X(80).\n       FD JOB-FILE.\n       01 JOB-REC PIC X(200).',
    )

if "WS-EOF-JOB" not in text:
    text = text.replace(
        '       01 WS-EOF-CALENDAR PIC X VALUE "N".',
        '       01 WS-EOF-CALENDAR PIC X VALUE "N".\n       01 WS-EOF-JOB PIC X VALUE "N".',
    )

if "WS-CYCLE-WINDOW-LIMIT" not in text:
    text = text.replace(
        '       01 WS-CYCLE-DAYS PIC 9(4) VALUE 0.',
        '       01 WS-CYCLE-DAYS PIC 9(4) VALUE 0.\n       01 WS-CYCLE-WINDOW-LIMIT PIC 9(4) VALUE 2.\n       01 WS-PROP-LINE PIC X(200).\n       01 WS-PROP-KEY PIC X(40).\n       01 WS-PROP-VALUE PIC X(40).\n       01 WS-PROP-NUM PIC 9(4) VALUE 0.',
    )

if "PERFORM LOAD-JOB-PROPS" not in text:
    if '       MAIN-PARA.\n           PERFORM LOAD-REASON-CODES\n           PERFORM LOAD-CALENDAR\n           OPEN INPUT WIRE-FILE' in text:
        text = text.replace(
            '       MAIN-PARA.\n           PERFORM LOAD-REASON-CODES\n           PERFORM LOAD-CALENDAR\n           OPEN INPUT WIRE-FILE',
            '       MAIN-PARA.\n           PERFORM LOAD-JOB-PROPS\n           PERFORM LOAD-REASON-CODES\n           PERFORM LOAD-CALENDAR\n           OPEN INPUT WIRE-FILE',
        )
    elif "       MAIN-PARA.\n           PERFORM LOAD-CALENDAR\n           OPEN INPUT WIRE-FILE" in text:
        text = text.replace(
            "       MAIN-PARA.\n           PERFORM LOAD-CALENDAR\n           OPEN INPUT WIRE-FILE",
            "       MAIN-PARA.\n           PERFORM LOAD-JOB-PROPS\n           PERFORM LOAD-CALENDAR\n           OPEN INPUT WIRE-FILE",
        )
    else:
        text = text.replace(
            "       MAIN-PARA.\n           PERFORM LOAD-CALENDAR",
            "       MAIN-PARA.\n           PERFORM LOAD-JOB-PROPS\n           PERFORM LOAD-CALENDAR",
        )

if "LOAD-JOB-PROPS." not in text:
    insert_at = text.index("       LOAD-CALENDAR.")
    block = """       LOAD-JOB-PROPS.
           MOVE 2 TO WS-CYCLE-WINDOW-LIMIT
           OPEN INPUT JOB-FILE
           PERFORM UNTIL WS-EOF-JOB = "Y"
               READ JOB-FILE
                   AT END
                       MOVE "Y" TO WS-EOF-JOB
                   NOT AT END
                       MOVE JOB-REC TO WS-PROP-LINE
                       UNSTRING WS-PROP-LINE DELIMITED BY "="
                           INTO WS-PROP-KEY WS-PROP-VALUE
                       END-UNSTRING
                       IF FUNCTION TRIM(WS-PROP-KEY) = "cycle_window_open_days"
                           IF FUNCTION TRIM(WS-PROP-VALUE) NOT = SPACES
                               MOVE 0 TO WS-PROP-NUM
                               MOVE FUNCTION NUMVAL(FUNCTION TRIM(WS-PROP-VALUE))
                                   TO WS-PROP-NUM
                               MOVE WS-PROP-NUM TO WS-CYCLE-WINDOW-LIMIT
                           END-IF
                       END-IF
               END-READ
           END-PERFORM
           CLOSE JOB-FILE.

"""
    text = text[:insert_at] + block + text[insert_at:]

text = text.replace("AND WS-CYCLE-DAYS <= 2", "AND WS-CYCLE-DAYS <= WS-CYCLE-WINDOW-LIMIT")

path.write_text(text)
PY

/app/scripts/run_batch.sh
test -s /app/out/wire_return_report.csv
test -s /app/out/wire_return_summary.txt
