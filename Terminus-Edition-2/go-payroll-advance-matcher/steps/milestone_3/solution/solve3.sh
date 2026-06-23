#!/usr/bin/env bash
set -euo pipefail


cd /app

python3 <<'PY'
from pathlib import Path

path = Path("/app/cmd/reconcile/main.go")
text = path.read_text()

text = text.replace(
    "type Advance struct {\n\tID       string\n\tCustomer string\n\tAmount   int\n\tStatus   string\n\tMethod   string\n}",
    "type Advance struct {\n\tID       string\n\tCustomer string\n\tAmount   int\n\tStatus   string\n\tMethod  string\n\tAdvanceDate  string\n}",
)
text = text.replace(
    "type Repayment struct {\n\tAdvanceID string\n\tCustomer  string\n\tAmount    int\n\tMethod    string\n}",
    "type Repayment struct {\n\tAdvanceID     string\n\tCustomer   string\n\tAmount     int\n\tMethod    string\n\tRepaymentDate string\n}",
)
text = text.replace(
    "out = append(out, Advance{ID: clean(row[0]), Customer: clean(row[1]), Amount: amount, Status: strings.ToUpper(clean(row[3])), Method: canonicalMethod(row[4])})",
    '''dueDate := ""
\t\tif len(row) > 5 {
\t\t\tdueDate = clean(row[5])
\t\t}
\t\tout = append(out, Advance{ID: clean(row[0]), Customer: clean(row[1]), Amount: amount, Status: strings.ToUpper(clean(row[3])), Method: canonicalMethod(row[4]), AdvanceDate: dueDate})''',
)
text = text.replace(
    "out = append(out, Repayment{AdvanceID: clean(row[0]), Customer: clean(row[1]), Amount: amount, Method: canonicalMethod(row[3])})",
    '''repaymentDate := ""
\t\tif len(row) > 4 {
\t\t\trepaymentDate = clean(row[4])
\t\t}
\t\tout = append(out, Repayment{AdvanceID: clean(row[0]), Customer: clean(row[1]), Amount: amount, Method: canonicalMethod(row[3]), RepaymentDate: repaymentDate})''',
)
text = text.replace(
    "return writeOutputs(advances, repayments)",
    '''openDates, err := loadOpenDates("/app/config/cutoff_calendar.txt")
\tif err != nil {
\t\treturn err
\t}
\treturn writeOutputs(advances, repayments, openDates)''',
)
text = text.replace(
    "func writeOutputs(advances []Advance, repayments []Repayment) error {",
    "func writeOutputs(advances []Advance, repayments []Repayment, openDates map[string]bool) error {",
)
text = text.replace(
    "matchIndex := findMatch(advances, repayment, usedAdvances)",
    "matchIndex := findMatch(advances, repayment, usedAdvances, openDates)",
)
start = text.index("func findMatch(")
end = text.index("\nfunc clean(", start)
text = text[:start] + '''func findMatch(advances []Advance, repayment Repayment, used []bool, openDates map[string]bool) int {
\tbestIndex := -1
\tfor i := range advances {
\t\tif used[i] {
\t\t\tcontinue
\t\t}
\t\tadvance := &advances[i]
\t\tif !openDates[repayment.RepaymentDate] ||
\t\t\trepayment.RepaymentDate == "" ||
\t\t\tadvance.AdvanceDate == "" ||
\t\t\trepayment.RepaymentDate > advance.AdvanceDate ||
\t\t\tadvance.ID != repayment.AdvanceID ||
\t\t\tadvance.Customer != repayment.Customer ||
\t\t\tadvance.Amount != repayment.Amount ||
\t\t\tadvance.Status != "ACTIVE" ||
\t\t\t!allowedMethod(advance.Method) ||
\t\t\tadvance.Method != repayment.Method {
\t\t\tcontinue
\t\t}
\t\tif bestIndex < 0 || advance.AdvanceDate > advances[bestIndex].AdvanceDate {
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
test -s /app/out/repayment_report.csv
test -s /app/out/repayment_summary.json
