#!/usr/bin/env bash
set -euo pipefail

cd /app

python3 <<'PY'
from pathlib import Path

path = Path("/app/cmd/reconcile/main.go")
text = path.read_text()
text = text.replace("loadOrders", "loadOrders")
text = text.replace('"strconv"', '"strconv"\n\t"strings"')
text = text.replace('amount, err := strconv.Atoi(row[2])', 'amount, err := strconv.Atoi(clean(row[2]))')
text = text.replace(
    'out = append(out, Order{ID: row[0], Cafe: row[1], Amount: amount, Status: row[3], Route: row[4]})',
    'out = append(out, Order{ID: clean(row[0]), Cafe: clean(row[1]), Amount: amount, Status: strings.ToUpper(clean(row[3])), Route: strings.ToUpper(clean(row[4]))})',
)
text = text.replace(
    'out = append(out, Credit{OrderID: row[0], Cafe: row[1], Amount: amount, Route: row[3]})',
    'out = append(out, Credit{OrderID: clean(row[0]), Cafe: clean(row[1]), Amount: amount, Route: strings.ToUpper(clean(row[3]))})',
)
text = text.replace(
    'summary.MatchedAmountCents -= credit.Amount',
    'summary.MatchedAmountCents += credit.Amount',
)
text = text.replace(
    'if len(order.ID) >= 8 && len(credit.OrderID) >= 8 &&\n\t\t\torder.ID[:8] == credit.OrderID[:8] &&',
    'if order.ID == credit.OrderID &&',
)
text = text.replace(
    'return route == "LOCAL" || route == "REGIONAL" || route == "EXPORT"',
    'return route == "LOCAL" || route == "REGIONAL" || route == "EXPORT"',
)
text = text.replace(
    '\tsummary := Summary{}\n\tfor _, credit := range credits {\n\t\tmatch := findMatch(orders, credit)',
    '\tsummary := Summary{}\n\tusedRecords := make([]bool, len(orders))\n\tfor _, credit := range credits {\n\t\tmatchIndex := findMatch(orders, credit, usedRecords)\n\t\tvar match *Order\n\t\tif matchIndex >= 0 {\n\t\t\tmatch = &orders[matchIndex]\n\t\t\tusedRecords[matchIndex] = true\n\t\t}',
)
text = text.replace(
    'func findMatch(orders []Order, credit Credit) *Order {\n\tfor i := range orders {\n\t\torder := &orders[i]\n\t\tif order.ID == credit.OrderID &&',
    'func findMatch(orders []Order, credit Credit, used []bool) int {\n\tfor i := range orders {\n\t\tif used[i] {\n\t\t\tcontinue\n\t\t}\n\t\torder := &orders[i]\n\t\tif order.ID == credit.OrderID &&',
)
text = text.replace(
    '\t\t\treturn order\n\t\t}\n\t}\n\treturn nil\n}',
    '\t\t\treturn i\n\t\t}\n\t}\n\treturn -1\n}',
)
text = text.replace(
    'func allowedRoute(route string) bool {\n\treturn route == "LOCAL" || route == "REGIONAL" || route == "EXPORT"\n}',
    'func clean(value string) string {\n\treturn strings.TrimSpace(value)\n}\n\nfunc allowedRoute(route string) bool {\n\troute = strings.ToUpper(clean(route))\n\treturn route == "LOCAL" || route == "REGIONAL" || route == "EXPORT"\n}',
)
path.write_text(text)
PY

/app/scripts/run_batch.sh
test -s /app/out/credit_report.csv
test -s /app/out/credit_summary.json
