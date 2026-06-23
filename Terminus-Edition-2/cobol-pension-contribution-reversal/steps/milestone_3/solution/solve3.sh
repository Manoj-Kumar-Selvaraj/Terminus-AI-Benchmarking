#!/usr/bin/env bash
set -euo pipefail

python3 <<'PY'
from pathlib import Path

path = Path("/app/src/pension_reversal_reconcile.cbl")
text = path.read_text()

replacements = [
    (
        """       01 ACT-REASON PIC X(3).
       01 ACT-BRANCH PIC X(4).""",
        """       01 ACT-REASON PIC X(3).
       01 ACT-BRANCH PIC X(4).
       01 ACT-ALLOCATION PIC X(2).""",
    ),
    (
        """             10 SRC-STATUS PIC X.
             10 SRC-BRANCH PIC X(4).
             10 SRC-USED PIC X.""",
        """             10 SRC-STATUS PIC X.
             10 SRC-BRANCH PIC X(4).
             10 SRC-ALLOCATION PIC X(2).
             10 SRC-USED PIC X.""",
    ),
    (
        """                       MOVE SRC-LINE(43:1) TO SRC-STATUS(SRC-COUNT)
                       MOVE SRC-LINE(44:4) TO SRC-BRANCH(SRC-COUNT)
                       MOVE "N" TO SRC-USED(SRC-COUNT)""",
        """                       MOVE SRC-LINE(43:1) TO SRC-STATUS(SRC-COUNT)
                       MOVE SRC-LINE(44:4) TO SRC-BRANCH(SRC-COUNT)
                       MOVE SRC-LINE(48:2) TO SRC-ALLOCATION(SRC-COUNT)
                       MOVE "N" TO SRC-USED(SRC-COUNT)""",
    ),
    (
        """           MOVE ACT-LINE(43:3) TO ACT-REASON
           MOVE ACT-LINE(46:4) TO ACT-BRANCH
           MOVE ACT-CAT TO CANON-CAT""",
        """           MOVE ACT-LINE(43:3) TO ACT-REASON
           MOVE ACT-LINE(46:4) TO ACT-BRANCH
           MOVE ACT-LINE(50:2) TO ACT-ALLOCATION
           MOVE ACT-CAT TO CANON-CAT""",
    ),
]
for old, new in replacements:
    if new not in text:
        if old not in text:
            raise SystemExit("milestone 3 allocation patch anchor missing")
        text = text.replace(old, new, 1)

old_loop = """           PERFORM VARYING I FROM 1 BY 1 UNTIL I > SRC-COUNT OR MATCHED-FLAG = "Y"
               MOVE SRC-DATE(I) TO CHECK-DATE
               PERFORM CHECK-CALENDAR
               IF ACT-ID = SRC-ID(I)
                  AND ACT-ACCT = SRC-ACCT(I)
                  AND CANON-CAT = SRC-CAT(I)
                  AND ACT-AMT = SRC-AMT(I)
                  AND SRC-BRANCH(I) = ACT-BRANCH
                  AND SRC-USED(I) NOT = "Y"
                  AND SRC-STATUS(I) = "P"
                  AND (SRC-CAT(I) = "EMP"
                    OR SRC-CAT(I) = "ERD"
                    OR SRC-CAT(I) = "VOL")
                  AND (ACT-REASON = "R02"
                    OR ACT-REASON = "R05"
                    OR ACT-REASON = "R14")
                  AND ACT-DATE IS NUMERIC
                  AND SRC-DATE(I) IS NUMERIC
                  AND ACT-DATE >= SRC-DATE(I)
                   MOVE "Y" TO MATCHED-FLAG
                   MOVE I TO MATCH-IDX
                   MOVE "Y" TO SRC-USED(I)
               END-IF
           END-PERFORM"""
new_loop = """           PERFORM VARYING I FROM 1 BY 1 UNTIL I > SRC-COUNT
               MOVE SRC-DATE(I) TO CHECK-DATE
               PERFORM CHECK-CALENDAR
               IF ACT-ID = SRC-ID(I)
                  AND ACT-ACCT = SRC-ACCT(I)
                  AND CANON-CAT = SRC-CAT(I)
                  AND ACT-AMT = SRC-AMT(I)
                  AND SRC-BRANCH(I) = ACT-BRANCH
                  AND SRC-USED(I) NOT = "Y"
                  AND SRC-STATUS(I) = "P"
                  AND (SRC-CAT(I) = "EMP"
                    OR SRC-CAT(I) = "ERD"
                    OR SRC-CAT(I) = "VOL")
                  AND (ACT-REASON = "R02"
                    OR ACT-REASON = "R05"
                    OR ACT-REASON = "R14")
                  AND ACT-DATE IS NUMERIC
                  AND SRC-DATE(I) IS NUMERIC
                  AND ACT-DATE >= SRC-DATE(I)
                  AND OPEN-FLAG = "Y"
                  AND (ACT-ALLOCATION = SPACES
                    OR ACT-ALLOCATION = SRC-ALLOCATION(I))
                   IF MATCHED-FLAG = "N"
                       MOVE "Y" TO MATCHED-FLAG
                       MOVE I TO MATCH-IDX
                   ELSE
                       IF SRC-DATE(I) > SRC-DATE(MATCH-IDX)
                          OR (SRC-DATE(I) = SRC-DATE(MATCH-IDX)
                            AND I < MATCH-IDX)
                           MOVE I TO MATCH-IDX
                       END-IF
                   END-IF
               END-IF
           END-PERFORM
           IF MATCHED-FLAG = "Y"
               MOVE "Y" TO SRC-USED(MATCH-IDX)
           END-IF"""
if new_loop not in text:
    if old_loop not in text:
        raise SystemExit("milestone 3 selection patch anchor missing")
    text = text.replace(old_loop, new_loop, 1)

old_state = """                      AND (CAL-STATE(CAL-IDX) = "OPEN"
                        OR CAL-STATE(CAL-IDX) = "open")"""
new_state = '''                      AND FUNCTION UPPER-CASE(CAL-STATE(CAL-IDX))
                          = "OPEN"'''
if new_state not in text:
    if old_state not in text:
        raise SystemExit("milestone 3 calendar state patch anchor missing")
    text = text.replace(old_state, new_state, 1)

path.write_text(text)
PY

/app/scripts/run_batch.sh
