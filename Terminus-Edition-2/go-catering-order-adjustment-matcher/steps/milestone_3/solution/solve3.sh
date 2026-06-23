#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STEPS_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"

cd /app

python3 <<'PY'
from pathlib import Path

path = Path("/app/cmd/reconcile/main.go")
text = path.read_text()

if '"os"' not in text:
    text = text.replace('"strconv"', '"os"\n\t"strconv"')

text = text.replace(
    "type Order struct {\n\tID       string\n\tCustomer string\n\tAmount   int\n\tStatus   string\n\tService   string\n}",
    "type Order struct {\n\tID       string\n\tCustomer string\n\tAmount   int\n\tStatus   string\n\tService  string\n\tFulfillDate  string\n}",
)
text = text.replace(
    "type Adjustment struct {\n\tOrderID string\n\tCustomer  string\n\tAmount    int\n\tService    string\n}",
    "type Adjustment struct {\n\tOrderID     string\n\tCustomer   string\n\tAmount     int\n\tService    string\n\tAdjustmentDate string\n}",
)
text = text.replace(
    "out = append(out, Order{ID: clean(row[0]), Customer: clean(row[1]), Amount: amount, Status: strings.ToUpper(clean(row[3])), Service: canonicalService(row[4])})",
    '''dueDate := ""
\t\tif len(row) > 5 {
\t\t\tdueDate = clean(row[5])
\t\t}
\t\tout = append(out, Order{ID: clean(row[0]), Customer: clean(row[1]), Amount: amount, Status: strings.ToUpper(clean(row[3])), Service: canonicalService(row[4]), FulfillDate: dueDate})''',
)
text = text.replace(
    "out = append(out, Adjustment{OrderID: clean(row[0]), Customer: clean(row[1]), Amount: amount, Service: canonicalService(row[3])})",
    '''adjustmentDate := ""
\t\tif len(row) > 4 {
\t\t\tadjustmentDate = clean(row[4])
\t\t}
\t\tout = append(out, Adjustment{OrderID: clean(row[0]), Customer: clean(row[1]), Amount: amount, Service: canonicalService(row[3]), AdjustmentDate: adjustmentDate})''',
)
text = text.replace(
    "return writeOutputs(orders, adjustments)",
    '''openDates, err := loadOpenDates("/app/config/cutoff_calendar.txt")
\tif err != nil {
\t\treturn err
\t}
\treturn writeOutputs(orders, adjustments, openDates)''',
)
text = text.replace(
    "func writeOutputs(orders []Order, adjustments []Adjustment) error {",
    "func writeOutputs(orders []Order, adjustments []Adjustment, openDates map[string]bool) error {",
)
text = text.replace(
    "matchIndex := findMatch(orders, adjustment, usedOrders)",
    "matchIndex := findMatch(orders, adjustment, usedOrders, openDates)",
)
start = text.index("func findMatch(")
end = text.index("\nfunc clean(", start)
text = text[:start] + '''func findMatch(orders []Order, adjustment Adjustment, used []bool, openDates map[string]bool) int {
\tbestIndex := -1
\tfor i := range orders {
\t\tif used[i] {
\t\t\tcontinue
\t\t}
\t\torder := &orders[i]
\t\tif !openDates[adjustment.AdjustmentDate] ||
\t\t\tadjustment.AdjustmentDate == "" ||
\t\t\torder.FulfillDate == "" ||
\t\t\tadjustment.AdjustmentDate > order.FulfillDate ||
\t\t\torder.ID != adjustment.OrderID ||
\t\t\torder.Customer != adjustment.Customer ||
\t\t\torder.Amount != adjustment.Amount ||
\t\t\torder.Status != "FULFILLED" ||
\t\t\t!allowedService(order.Service) ||
\t\t\torder.Service != adjustment.Service {
\t\t\tcontinue
\t\t}
\t\tif bestIndex < 0 || order.FulfillDate > orders[bestIndex].FulfillDate {
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
test -s /app/out/adjustment_report.csv
test -s /app/out/adjustment_summary.json
