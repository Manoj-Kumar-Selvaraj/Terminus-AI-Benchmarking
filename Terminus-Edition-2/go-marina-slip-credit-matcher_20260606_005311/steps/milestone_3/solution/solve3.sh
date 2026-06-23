#!/usr/bin/env bash
set -euo pipefail

cd /app

python3 <<'PY'
from pathlib import Path

path = Path("/app/cmd/reconcile/main.go")
text = path.read_text()
if '"os"' not in text:
    text = text.replace('"fmt"\n', '"fmt"\n\t"os"\n')

text = text.replace(
    "type Slip struct {\n\tID       string\n\tCustomer string\n\tAmount   int\n\tStatus   string\n\tDockZone   string\n}",
    "type Slip struct {\n\tID       string\n\tCustomer string\n\tAmount   int\n\tStatus   string\n\tDockZone  string\n\tDepartureDate  string\n}",
)
text = text.replace(
    "type Credit struct {\n\tSlipID string\n\tCustomer  string\n\tAmount    int\n\tDockZone    string\n}",
    "type Credit struct {\n\tSlipID     string\n\tCustomer   string\n\tAmount     int\n\tDockZone    string\n\tCreditDate string\n}",
)
text = text.replace(
    "out = append(out, Slip{ID: clean(row[0]), Customer: clean(row[1]), Amount: amount, Status: strings.ToUpper(clean(row[3])), DockZone: canonicalDockZone(row[4])})",
    '''dueDate := ""
\t\tif len(row) > 5 {
\t\t\tdueDate = clean(row[5])
\t\t}
\t\tout = append(out, Slip{ID: clean(row[0]), Customer: clean(row[1]), Amount: amount, Status: strings.ToUpper(clean(row[3])), DockZone: canonicalDockZone(row[4]), DepartureDate: dueDate})''',
)
text = text.replace(
    "out = append(out, Credit{SlipID: clean(row[0]), Customer: clean(row[1]), Amount: amount, DockZone: canonicalDockZone(row[3])})",
    '''creditDate := ""
\t\tif len(row) > 4 {
\t\t\tcreditDate = clean(row[4])
\t\t}
\t\tout = append(out, Credit{SlipID: clean(row[0]), Customer: clean(row[1]), Amount: amount, DockZone: canonicalDockZone(row[3]), CreditDate: creditDate})''',
)
text = text.replace(
    "return writeOutputs(slips, credits)",
    '''openDates, err := loadOpenDates("/app/config/cutoff_calendar.txt")
\tif err != nil {
\t\treturn err
\t}
\treturn writeOutputs(slips, credits, openDates)''',
)
text = text.replace(
    "func writeOutputs(slips []Slip, credits []Credit) error {",
    "func writeOutputs(slips []Slip, credits []Credit, openDates map[string]bool) error {",
)
text = text.replace(
    "matchIndex := findMatch(slips, credit, usedSlips)",
    "matchIndex := findMatch(slips, credit, usedSlips, openDates)",
)
start = text.index("func findMatch(")
end = text.index("\nfunc clean(", start)
text = text[:start] + '''func findMatch(slips []Slip, credit Credit, used []bool, openDates map[string]bool) int {
\tbestIndex := -1
\tfor i := range slips {
\t\tif used[i] {
\t\t\tcontinue
\t\t}
\t\tslip := &slips[i]
\t\tif !openDates[credit.CreditDate] ||
\t\t\tcredit.CreditDate == "" ||
\t\t\tslip.DepartureDate == "" ||
\t\t\tcredit.CreditDate > slip.DepartureDate ||
\t\t\tslip.ID != credit.SlipID ||
\t\t\tslip.Customer != credit.Customer ||
\t\t\tslip.Amount != credit.Amount ||
\t\t\tslip.Status != "DOCKED" ||
\t\t\t!allowedDockZone(slip.DockZone) ||
\t\t\tslip.DockZone != credit.DockZone {
\t\t\tcontinue
\t\t}
\t\tif bestIndex < 0 || slip.DepartureDate > slips[bestIndex].DepartureDate {
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
