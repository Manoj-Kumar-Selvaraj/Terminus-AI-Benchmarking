#!/usr/bin/env bash
set -euo pipefail

cd /app

python3 <<'PY'
from pathlib import Path

path = Path("/app/cmd/reconcile/main.go")
text = path.read_text()

text = text.replace(
    "type Lease struct {\n\tID       string\n\tCustomer string\n\tAmount   int\n\tStatus   string\n\tUnitType   string\n}",
    "type Lease struct {\n\tID       string\n\tCustomer string\n\tAmount   int\n\tStatus   string\n\tUnitType  string\n\tLeaseEnd  string\n}",
)
text = text.replace(
    "type Credit struct {\n\tLeaseID string\n\tCustomer  string\n\tAmount    int\n\tUnitType    string\n}",
    "type Credit struct {\n\tLeaseID     string\n\tCustomer   string\n\tAmount     int\n\tUnitType    string\n\tCreditDate string\n}",
)
text = text.replace(
    "out = append(out, Lease{ID: clean(row[0]), Customer: clean(row[1]), Amount: amount, Status: strings.ToUpper(clean(row[3])), UnitType: canonicalUnitType(row[4])})",
    '''dueDate := ""
\t\tif len(row) > 5 {
\t\t\tdueDate = clean(row[5])
\t\t}
\t\tout = append(out, Lease{ID: clean(row[0]), Customer: clean(row[1]), Amount: amount, Status: strings.ToUpper(clean(row[3])), UnitType: canonicalUnitType(row[4]), LeaseEnd: dueDate})''',
)
text = text.replace(
    "out = append(out, Credit{LeaseID: clean(row[0]), Customer: clean(row[1]), Amount: amount, UnitType: canonicalUnitType(row[3])})",
    '''creditDate := ""
\t\tif len(row) > 4 {
\t\t\tcreditDate = clean(row[4])
\t\t}
\t\tout = append(out, Credit{LeaseID: clean(row[0]), Customer: clean(row[1]), Amount: amount, UnitType: canonicalUnitType(row[3]), CreditDate: creditDate})''',
)
text = text.replace(
    "return writeOutputs(leases, credits)",
    '''openDates, err := loadOpenDates("/app/config/cutoff_calendar.txt")
\tif err != nil {
\t\treturn err
\t}
\treturn writeOutputs(leases, credits, openDates)''',
)
text = text.replace(
    "func writeOutputs(leases []Lease, credits []Credit) error {",
    "func writeOutputs(leases []Lease, credits []Credit, openDates map[string]bool) error {",
)
text = text.replace(
    "matchIndex := findMatch(leases, credit, usedLeases)",
    "matchIndex := findMatch(leases, credit, usedLeases, openDates)",
)
start = text.index("func findMatch(")
end = text.index("\nfunc clean(", start)
text = text[:start] + '''func findMatch(leases []Lease, credit Credit, used []bool, openDates map[string]bool) int {
\tbestIndex := -1
\tfor i := range leases {
\t\tif used[i] {
\t\t\tcontinue
\t\t}
\t\tlease := &leases[i]
\t\tif !openDates[credit.CreditDate] ||
\t\t\tcredit.CreditDate == "" ||
\t\t\tlease.LeaseEnd == "" ||
\t\t\tcredit.CreditDate > lease.LeaseEnd ||
\t\t\tlease.ID != credit.LeaseID ||
\t\t\tlease.Customer != credit.Customer ||
\t\t\tlease.Amount != credit.Amount ||
\t\t\tlease.Status != "ACTIVE" ||
\t\t\t!allowedUnitType(lease.UnitType) ||
\t\t\tlease.UnitType != credit.UnitType {
\t\t\tcontinue
\t\t}
\t\tif bestIndex < 0 || lease.LeaseEnd > leases[bestIndex].LeaseEnd {
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
