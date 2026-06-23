#!/usr/bin/env bash
set -euo pipefail

cd /app

python3 <<'PY'
from pathlib import Path

path = Path("/app/cmd/reconcile/main.go")
text = path.read_text()

text = text.replace(
    "type Order struct {\n\tID       string\n\tCafe     string\n\tAmount   int\n\tStatus   string\n\tRoute    string\n}",
    "type Order struct {\n\tID          string\n\tCafe    string\n\tAmount      int\n\tStatus      string\n\tRoute       string\n\tBakeDate    string\n\tHasBakeDate bool\n}",
)
text = text.replace(
    "type Credit struct {\n\tOrderID string\n\tCafe    string\n\tAmount  int\n\tRoute   string\n}",
    "type Credit struct {\n\tOrderID       string\n\tCafe      string\n\tAmount        int\n\tRoute         string\n\tCreditDate    string\n\tHasCreditDate bool\n}",
)
text = text.replace(
    "out = append(out, Order{ID: clean(row[0]), Cafe: clean(row[1]), Amount: amount, Status: strings.ToUpper(clean(row[3])), Route: canonicalRoute(row[4])})",
    '''bakeDate := ""
\t\thasBakeDate := len(row) > 5
\t\tif len(row) > 5 {
\t\t\tbakeDate = clean(row[5])
\t\t}
\t\tout = append(out, Order{ID: clean(row[0]), Cafe: clean(row[1]), Amount: amount, Status: strings.ToUpper(clean(row[3])), Route: canonicalRoute(row[4]), BakeDate: bakeDate, HasBakeDate: hasBakeDate})''',
)
text = text.replace(
    "out = append(out, Credit{OrderID: clean(row[0]), Cafe: clean(row[1]), Amount: amount, Route: canonicalRoute(row[3])})",
    '''creditDate := ""
\t\thasCreditDate := len(row) > 4
\t\tif len(row) > 4 {
\t\t\tcreditDate = clean(row[4])
\t\t}
\t\tout = append(out, Credit{OrderID: clean(row[0]), Cafe: clean(row[1]), Amount: amount, Route: canonicalRoute(row[3]), CreditDate: creditDate, HasCreditDate: hasCreditDate})''',
)
text = text.replace(
    "return writeOutputs(orders, credits)",
    '''openDates, err := loadOpenDates("/app/config/cutoff_calendar.txt")
\tif err != nil {
\t\treturn err
\t}
\treturn writeOutputs(orders, credits, openDates)''',
)
text = text.replace(
    "func writeOutputs(orders []Order, credits []Credit) error {",
    "func writeOutputs(orders []Order, credits []Credit, openDates map[string]bool) error {",
)
text = text.replace(
    "matchIndex := findMatch(orders, credit, usedRecords)",
    "matchIndex := findMatch(orders, credit, usedRecords, openDates)",
)
start = text.index("func findMatch(")
end = text.index("\nfunc clean(", start)
text = text[:start] + '''func findMatch(orders []Order, credit Credit, used []bool, openDates map[string]bool) int {
\tbestIndex := -1
\tfor i := range orders {
\t\tif used[i] {
\t\t\tcontinue
\t\t}
\t\torder := &orders[i]
\t\tif order.ID != credit.OrderID ||
\t\t\torder.Cafe != credit.Cafe ||
\t\t\torder.Amount != credit.Amount ||
\t\t\torder.Status != "FULFILLED" ||
\t\t\t!allowedRoute(order.Route) ||
\t\t\torder.Route != credit.Route {
\t\t\tcontinue
\t\t}
\t\tdateSchemaActive := credit.HasCreditDate || order.HasBakeDate
\t\tif dateSchemaActive &&
\t\t\t(credit.CreditDate == "" ||
\t\t\t\torder.BakeDate == "" ||
\t\t\t\t!openDates[credit.CreditDate] ||
\t\t\t\tcredit.CreditDate > order.BakeDate) {
\t\t\tcontinue
\t\t}
\t\tif bestIndex < 0 ||
\t\t\torder.BakeDate > orders[bestIndex].BakeDate ||
\t\t\t(order.BakeDate == orders[bestIndex].BakeDate && i < bestIndex) {
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
\t\tif len(fields) == 2 && strings.EqualFold(fields[1], "open") {
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
