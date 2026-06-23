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
    'out = append(out, Order{ID: row[0], Customer: row[1], Amount: amount, Status: row[3], Service: row[4]})',
    'out = append(out, Order{ID: clean(row[0]), Customer: clean(row[1]), Amount: amount, Status: strings.ToUpper(clean(row[3])), Service: strings.ToUpper(clean(row[4]))})',
)
text = text.replace(
    'out = append(out, Adjustment{OrderID: row[0], Customer: row[1], Amount: amount, Service: row[3]})',
    'out = append(out, Adjustment{OrderID: clean(row[0]), Customer: clean(row[1]), Amount: amount, Service: strings.ToUpper(clean(row[3]))})',
)
text = text.replace(
    'summary.MatchedAmountCents -= adjustment.Amount',
    'summary.MatchedAmountCents += adjustment.Amount',
)
text = text.replace(
    'if len(order.ID) >= 8 && len(adjustment.OrderID) >= 8 &&\n\t\t\torder.ID[:8] == adjustment.OrderID[:8] &&',
    'if order.ID == adjustment.OrderID &&',
)
text = text.replace(
    'return service == "PICKUP" || service == "DELIVERY" || service == "ONSITE"',
    'return service == "PICKUP" || service == "DELIVERY" || service == "ONSITE"',
)
text = text.replace(
    '\tsummary := Summary{}\n\tfor _, adjustment := range adjustments {\n\t\tmatch := findMatch(orders, adjustment)',
    '\tsummary := Summary{}\n\tusedOrders := make([]bool, len(orders))\n\tfor _, adjustment := range adjustments {\n\t\tmatchIndex := findMatch(orders, adjustment, usedOrders)\n\t\tvar match *Order\n\t\tif matchIndex >= 0 {\n\t\t\tmatch = &orders[matchIndex]\n\t\t\tusedOrders[matchIndex] = true\n\t\t}',
)
text = text.replace(
    'func findMatch(orders []Order, adjustment Adjustment) *Order {\n\tfor i := range orders {\n\t\torder := &orders[i]\n\t\tif order.ID == adjustment.OrderID &&',
    'func findMatch(orders []Order, adjustment Adjustment, used []bool) int {\n\tfor i := range orders {\n\t\tif used[i] {\n\t\t\tcontinue\n\t\t}\n\t\torder := &orders[i]\n\t\tif order.ID == adjustment.OrderID &&',
)
text = text.replace(
    '\t\t\treturn order\n\t\t}\n\t}\n\treturn nil\n}',
    '\t\t\treturn i\n\t\t}\n\t}\n\treturn -1\n}',
)
text = text.replace(
    'func allowedService(service string) bool {\n\treturn service == "PICKUP" || service == "DELIVERY" || service == "ONSITE"\n}',
    'func clean(value string) string {\n\treturn strings.TrimSpace(value)\n}\n\nfunc allowedService(service string) bool {\n\tservice = strings.ToUpper(clean(service))\n\treturn service == "PICKUP" || service == "DELIVERY" || service == "ONSITE"\n}',
)
path.write_text(text)
PY

/app/scripts/run_batch.sh
test -s /app/out/adjustment_report.csv
test -s /app/out/adjustment_summary.json
