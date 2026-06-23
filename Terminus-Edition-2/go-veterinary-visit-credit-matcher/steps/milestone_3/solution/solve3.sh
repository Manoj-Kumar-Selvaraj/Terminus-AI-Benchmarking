#!/usr/bin/env bash
set -euo pipefail

cd /app

python3 <<'PY'
from pathlib import Path

path = Path("/app/cmd/reconcile/main.go")
text = path.read_text()

text = text.replace(
    "type Visit struct {\n\tID       string\n\tCustomer string\n\tAmount   int\n\tStatus   string\n\tClinic   string\n}",
    "type Visit struct {\n\tID             string\n\tCustomer       string\n\tAmount         int\n\tStatus         string\n\tClinic         string\n\tServiceDate    string\n\tHasServiceDate bool\n}",
)
text = text.replace(
    "type Credit struct {\n\tVisitID  string\n\tCustomer string\n\tAmount   int\n\tClinic   string\n}",
    "type Credit struct {\n\tVisitID        string\n\tCustomer       string\n\tAmount         int\n\tClinic         string\n\tCreditDate     string\n\tHasCreditDate  bool\n}",
)
text = text.replace(
    "out = append(out, Visit{ID: clean(row[0]), Customer: clean(row[1]), Amount: amount, Status: strings.ToUpper(clean(row[3])), Clinic: canonicalClinic(row[4])})",
    '''serviceDate := ""
\t\thasServiceDate := len(row) > 5
\t\tif len(row) > 5 {
\t\t\tserviceDate = clean(row[5])
\t\t}
\t\tout = append(out, Visit{ID: clean(row[0]), Customer: clean(row[1]), Amount: amount, Status: strings.ToUpper(clean(row[3])), Clinic: canonicalClinic(row[4]), ServiceDate: serviceDate, HasServiceDate: hasServiceDate})''',
)
text = text.replace(
    "out = append(out, Credit{VisitID: clean(row[0]), Customer: clean(row[1]), Amount: amount, Clinic: canonicalClinic(row[3])})",
    '''creditDate := ""
\t\thasCreditDate := len(row) > 4
\t\tif len(row) > 4 {
\t\t\tcreditDate = clean(row[4])
\t\t}
\t\tout = append(out, Credit{VisitID: clean(row[0]), Customer: clean(row[1]), Amount: amount, Clinic: canonicalClinic(row[3]), CreditDate: creditDate, HasCreditDate: hasCreditDate})''',
)
text = text.replace(
    "return writeOutputs(visits, credits)",
    '''openDates, err := loadOpenDates("/app/config/cutoff_calendar.txt")
\tif err != nil {
\t\treturn err
\t}
\treturn writeOutputs(visits, credits, openDates)''',
)
text = text.replace(
    "func writeOutputs(visits []Visit, credits []Credit) error {",
    "func writeOutputs(visits []Visit, credits []Credit, openDates map[string]bool) error {",
)
text = text.replace(
    "matchIndex := findMatch(visits, credit, usedVisits)",
    "matchIndex := findMatch(visits, credit, usedVisits, openDates)",
)
start = text.index("func findMatch(")
end = text.index("\nfunc clean(", start)
text = text[:start] + '''func findMatch(visits []Visit, credit Credit, used []bool, openDates map[string]bool) int {
\tbestIndex := -1
\tfor i := range visits {
\t\tif used[i] {
\t\t\tcontinue
\t\t}
\t\tvisit := &visits[i]
\t\tif visit.ID != credit.VisitID ||
\t\t\tvisit.Customer != credit.Customer ||
\t\t\tvisit.Amount != credit.Amount ||
\t\t\tvisit.Status != "CLOSED" ||
\t\t\t!allowedClinic(visit.Clinic) ||
\t\t\tvisit.Clinic != credit.Clinic {
\t\t\tcontinue
\t\t}
\t\tdateSchemaActive := credit.HasCreditDate || visit.HasServiceDate
\t\tif dateSchemaActive &&
\t\t\t(credit.CreditDate == "" ||
\t\t\t\tvisit.ServiceDate == "" ||
\t\t\t\t!openDates[credit.CreditDate] ||
\t\t\t\tcredit.CreditDate > visit.ServiceDate) {
\t\t\tcontinue
\t\t}
\t\tif bestIndex < 0 || visit.ServiceDate > visits[bestIndex].ServiceDate {
\t\t\tbestIndex = i
\t\t} else if visit.ServiceDate == visits[bestIndex].ServiceDate && i < bestIndex {
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
