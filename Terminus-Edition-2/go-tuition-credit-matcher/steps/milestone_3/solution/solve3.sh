#!/usr/bin/env bash
set -euo pipefail

cd /app

python3 <<'PY'
from pathlib import Path

path = Path("/app/cmd/reconcile/main.go")
text = path.read_text()

text = text.replace(
    "type Enrollment struct {\n\tID       string\n\tCustomer string\n\tAmount   int\n\tStatus   string\n\tTerm   string\n}",
    "type Enrollment struct {\n\tID       string\n\tCustomer string\n\tAmount   int\n\tStatus   string\n\tTerm  string\n\tSessionEnd  string\n}",
)
text = text.replace(
    "type Credit struct {\n\tEnrollmentID string\n\tCustomer  string\n\tAmount    int\n\tTerm    string\n}",
    "type Credit struct {\n\tEnrollmentID     string\n\tCustomer   string\n\tAmount     int\n\tTerm    string\n\tCreditDate string\n}",
)
text = text.replace(
    "out = append(out, Enrollment{ID: clean(row[0]), Customer: clean(row[1]), Amount: amount, Status: strings.ToUpper(clean(row[3])), Term: canonicalTerm(row[4])})",
    '''dueDate := ""
\t\tif len(row) > 5 {
\t\t\tdueDate = clean(row[5])
\t\t}
\t\tout = append(out, Enrollment{ID: clean(row[0]), Customer: clean(row[1]), Amount: amount, Status: strings.ToUpper(clean(row[3])), Term: canonicalTerm(row[4]), SessionEnd: dueDate})''',
)
text = text.replace(
    "out = append(out, Credit{EnrollmentID: clean(row[0]), Customer: clean(row[1]), Amount: amount, Term: canonicalTerm(row[3])})",
    '''creditDate := ""
\t\tif len(row) > 4 {
\t\t\tcreditDate = clean(row[4])
\t\t}
\t\tout = append(out, Credit{EnrollmentID: clean(row[0]), Customer: clean(row[1]), Amount: amount, Term: canonicalTerm(row[3]), CreditDate: creditDate})''',
)
text = text.replace(
    "return writeOutputs(enrollments, credits)",
    '''openDates, err := loadOpenDates("/app/config/cutoff_calendar.txt")
\tif err != nil {
\t\treturn err
\t}
\treturn writeOutputs(enrollments, credits, openDates)''',
)
text = text.replace(
    "func writeOutputs(enrollments []Enrollment, credits []Credit) error {",
    "func writeOutputs(enrollments []Enrollment, credits []Credit, openDates map[string]bool) error {",
)
text = text.replace(
    "matchIndex := findMatch(enrollments, credit, usedEnrollments)",
    "matchIndex := findMatch(enrollments, credit, usedEnrollments, openDates)",
)
start = text.index("func findMatch(")
end = text.index("\nfunc clean(", start)
text = text[:start] + '''func findMatch(enrollments []Enrollment, credit Credit, used []bool, openDates map[string]bool) int {
\tbestIndex := -1
\tfor i := range enrollments {
\t\tif used[i] {
\t\t\tcontinue
\t\t}
\t\tenrollment := &enrollments[i]
\t\tif !openDates[credit.CreditDate] ||
\t\t\tcredit.CreditDate == "" ||
\t\t\tenrollment.SessionEnd == "" ||
\t\t\tcredit.CreditDate > enrollment.SessionEnd ||
\t\t\tenrollment.ID != credit.EnrollmentID ||
\t\t\tenrollment.Customer != credit.Customer ||
\t\t\tenrollment.Amount != credit.Amount ||
\t\t\tenrollment.Status != "ENROLLED" ||
\t\t\t!allowedTerm(enrollment.Term) ||
\t\t\tenrollment.Term != credit.Term {
\t\t\tcontinue
\t\t}
\t\tif bestIndex < 0 || enrollment.SessionEnd > enrollments[bestIndex].SessionEnd {
\t\t\tbestIndex = i
\t\t}
\t}
\treturn bestIndex
}

func loadOpenDates(path string) (map[string]bool, error) {
\tdata, err := os.ReadFile(path)
\tif err != nil {
\t\treturn nil, err
\t}
\topenDates := map[string]bool{}
\tfor _, line := range strings.Split(string(data), "\\n") {
\t\tfields := strings.Fields(line)
\t\tif len(fields) >= 2 && strings.EqualFold(fields[1], "open") {
\t\t\topenDates[fields[0]] = true
\t\t}
\t}
\treturn openDates, nil
}
''' + text[end:]

path.write_text(text)
PY

/app/scripts/run_batch.sh
test -s /app/out/credit_report.csv
test -s /app/out/credit_summary.json
