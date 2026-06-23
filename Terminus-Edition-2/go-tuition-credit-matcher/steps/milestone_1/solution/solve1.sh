#!/usr/bin/env bash
set -euo pipefail

cd /app

python3 <<'PY'
from pathlib import Path

path = Path("/app/cmd/reconcile/main.go")
text = path.read_text()
text = text.replace('"strconv"', '"strconv"\n\t"strings"')
text = text.replace('amount, err := strconv.Atoi(row[2])', 'amount, err := strconv.Atoi(clean(row[2]))')
text = text.replace(
    'out = append(out, Enrollment{ID: row[0], Customer: row[1], Amount: amount, Status: row[3], Term: row[4]})',
    'out = append(out, Enrollment{ID: clean(row[0]), Customer: clean(row[1]), Amount: amount, Status: strings.ToUpper(clean(row[3])), Term: strings.ToUpper(clean(row[4]))})',
)
text = text.replace(
    'out = append(out, Credit{EnrollmentID: row[0], Customer: row[1], Amount: amount, Term: row[3]})',
    'out = append(out, Credit{EnrollmentID: clean(row[0]), Customer: clean(row[1]), Amount: amount, Term: strings.ToUpper(clean(row[3]))})',
)
text = text.replace(
    'summary.MatchedAmountCents -= credit.Amount',
    'summary.MatchedAmountCents += credit.Amount',
)
text = text.replace(
    'if len(enrollment.ID) >= 8 && len(credit.EnrollmentID) >= 8 &&\n\t\t\tenrollment.ID[:8] == credit.EnrollmentID[:8] &&',
    'if enrollment.ID == credit.EnrollmentID &&',
)
text = text.replace(
    'return term == "ONL" || term == "MAIL" || term == "CAMP"',
    'return term == "ONL" || term == "MAIL" || term == "CAMP"',
)
text = text.replace(
    '\tsummary := Summary{}\n\tfor _, credit := range credits {\n\t\tmatch := findMatch(enrollments, credit)',
    '\tsummary := Summary{}\n\tusedEnrollments := make([]bool, len(enrollments))\n\tfor _, credit := range credits {\n\t\tmatchIndex := findMatch(enrollments, credit, usedEnrollments)\n\t\tvar match *Enrollment\n\t\tif matchIndex >= 0 {\n\t\t\tmatch = &enrollments[matchIndex]\n\t\t\tusedEnrollments[matchIndex] = true\n\t\t}',
)
text = text.replace(
    'func findMatch(enrollments []Enrollment, credit Credit) *Enrollment {\n\tfor i := range enrollments {\n\t\tenrollment := &enrollments[i]\n\t\tif enrollment.ID == credit.EnrollmentID &&',
    'func findMatch(enrollments []Enrollment, credit Credit, used []bool) int {\n\tfor i := range enrollments {\n\t\tif used[i] {\n\t\t\tcontinue\n\t\t}\n\t\tenrollment := &enrollments[i]\n\t\tif enrollment.ID == credit.EnrollmentID &&',
)
text = text.replace(
    '\t\t\treturn enrollment\n\t\t}\n\t}\n\treturn nil\n}',
    '\t\t\treturn i\n\t\t}\n\t}\n\treturn -1\n}',
)
text = text.replace(
    'func allowedTerm(term string) bool {\n\treturn term == "ONL" || term == "MAIL" || term == "CAMP"\n}',
    'func clean(value string) string {\n\treturn strings.TrimSpace(value)\n}\n\nfunc allowedTerm(term string) bool {\n\tterm = strings.ToUpper(clean(term))\n\treturn term == "ONL" || term == "MAIL" || term == "CAMP"\n}',
)
path.write_text(text)
PY

/app/scripts/run_batch.sh
test -s /app/out/credit_report.csv
test -s /app/out/credit_summary.json
