#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

cd /app

if grep -q 'func fileHasColumn' /app/cmd/reconcile/main.go; then
  /app/scripts/run_batch.sh
  test -s /app/out/credit_report.csv
  test -s /app/out/credit_summary.json
  exit 0
fi

if ! grep -q 'func canonicalChannel' /app/cmd/reconcile/main.go; then
  bash "$SCRIPT_DIR/solve2.sh"
fi

python3 <<'PY'
from pathlib import Path

path = Path("/app/cmd/reconcile/main.go")
text = path.read_text()

text = text.replace(
    "type Visit struct {\n\tID       string\n\tCustomer string\n\tAmount   int\n\tStatus   string\n\tChannel   string\n}",
    "type Visit struct {\n\tID       string\n\tCustomer string\n\tAmount   int\n\tStatus   string\n\tChannel  string\n\tDueDate  string\n}",
)
text = text.replace(
    "type Credit struct {\n\tVisitID string\n\tCustomer  string\n\tAmount    int\n\tChannel    string\n}",
    "type Credit struct {\n\tVisitID     string\n\tCustomer   string\n\tAmount     int\n\tChannel    string\n\tCreditDate string\n}",
)
text = text.replace(
    "out = append(out, Visit{ID: clean(row[0]), Customer: clean(row[1]), Amount: amount, Status: strings.ToUpper(clean(row[3])), Channel: canonicalChannel(row[4])})",
    '''dueDate := ""
\t\tif len(row) > 5 {
\t\t\tdueDate = clean(row[5])
\t\t}
\t\tout = append(out, Visit{ID: clean(row[0]), Customer: clean(row[1]), Amount: amount, Status: strings.ToUpper(clean(row[3])), Channel: canonicalChannel(row[4]), DueDate: dueDate})''',
)
text = text.replace(
    "out = append(out, Credit{VisitID: clean(row[0]), Customer: clean(row[1]), Amount: amount, Channel: canonicalChannel(row[3])})",
    '''creditDate := ""
\t\tif len(row) > 4 {
\t\t\tcreditDate = clean(row[4])
\t\t}
\t\tout = append(out, Credit{VisitID: clean(row[0]), Customer: clean(row[1]), Amount: amount, Channel: canonicalChannel(row[3]), CreditDate: creditDate})''',
)
text = text.replace(
    "return writeOutputs(visits, credits)",
    '''openDates, err := loadOpenDates("/app/config/cutoff_calendar.txt")
\tif err != nil {
\t\treturn err
\t}
\tdated := fileHasColumn("/app/data/visits.csv", "due_date") ||
\t\tfileHasColumn("/app/data/credits.csv", "credit_date")
\treturn writeOutputs(visits, credits, openDates, dated)''',
)
text = text.replace(
    "func writeOutputs(visits []Visit, credits []Credit) error {",
    "func writeOutputs(visits []Visit, credits []Credit, openDates map[string]bool, dated bool) error {",
)
text = text.replace(
    "matchIndex := findMatch(visits, credit, usedVisits)",
    "matchIndex := findMatch(visits, credit, usedVisits, openDates, dated)",
)
start = text.index("func findMatch(")
end = text.index("\nfunc clean(", start)
text = text[:start] + '''func findMatch(visits []Visit, credit Credit, used []bool, openDates map[string]bool, dated bool) int {
\tbestIndex := -1
\tfor i := range visits {
\t\tif used[i] {
\t\t\tcontinue
\t\t}
\t\tvisit := &visits[i]
\t\tif dated {
\t\t\tif credit.CreditDate == "" || visit.DueDate == "" ||
\t\t\t\t!openDates[credit.CreditDate] ||
\t\t\t\tcredit.CreditDate > visit.DueDate {
\t\t\t\tcontinue
\t\t\t}
\t\t}
\t\tif visit.ID != credit.VisitID ||
\t\t\tvisit.Customer != credit.Customer ||
\t\t\tvisit.Amount != credit.Amount ||
\t\t\tvisit.Status != "POSTED" ||
\t\t\t!allowedChannel(visit.Channel) ||
\t\t\tvisit.Channel != credit.Channel {
\t\t\tcontinue
\t\t}
\t\tif bestIndex < 0 ||
\t\t\tvisit.DueDate > visits[bestIndex].DueDate ||
\t\t\t(dated && visit.DueDate == visits[bestIndex].DueDate && i < bestIndex) {
\t\t\tbestIndex = i
\t\t}
\t}
\treturn bestIndex
}

func fileHasColumn(path, column string) bool {
\tf, err := os.Open(path)
\tif err != nil {
\t\treturn false
\t}
\tdefer f.Close()
\treader := csv.NewReader(f)
\theader, err := reader.Read()
\tif err != nil {
\t\treturn false
\t}
\tfor _, field := range header {
\t\tif strings.EqualFold(clean(field), column) {
\t\t\treturn true
\t\t}
\t}
\treturn false
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
