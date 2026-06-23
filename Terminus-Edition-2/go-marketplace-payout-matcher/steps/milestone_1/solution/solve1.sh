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
    'out = append(out, Order{ID: row[0], Customer: row[1], Amount: amount, Status: row[3], Lane: row[4]})',
    'out = append(out, Order{ID: clean(row[0]), Customer: clean(row[1]), Amount: amount, Status: strings.ToUpper(clean(row[3])), Lane: strings.ToUpper(clean(row[4]))})',
)
text = text.replace(
    'out = append(out, Payout{OrderID: row[0], Customer: row[1], Amount: amount, Lane: row[3]})',
    'out = append(out, Payout{OrderID: clean(row[0]), Customer: clean(row[1]), Amount: amount, Lane: strings.ToUpper(clean(row[3]))})',
)
text = text.replace(
    'summary.MatchedAmountCents -= payout.Amount',
    'summary.MatchedAmountCents += payout.Amount',
)
text = text.replace(
    'if len(order.ID) >= 8 && len(payout.OrderID) >= 8 &&\n\t\t\torder.ID[:8] == payout.OrderID[:8] &&',
    'if order.ID == payout.OrderID &&',
)
text = text.replace(
    '\tsummary := Summary{}\n\tfor _, payout := range payouts {\n\t\tmatch := findMatch(orders, payout)',
    '\tsummary := Summary{}\n\tusedOrders := make([]bool, len(orders))\n\tfor _, payout := range payouts {\n\t\tmatchIndex := findMatch(orders, payout, usedOrders)\n\t\tvar match *Order\n\t\tif matchIndex >= 0 {\n\t\t\tmatch = &orders[matchIndex]\n\t\t\tusedOrders[matchIndex] = true\n\t\t}',
)
text = text.replace(
    'func findMatch(orders []Order, payout Payout) *Order {\n\tfor i := range orders {\n\t\torder := &orders[i]\n\t\tif order.ID == payout.OrderID &&',
    'func findMatch(orders []Order, payout Payout, used []bool) int {\n\tfor i := range orders {\n\t\tif used[i] {\n\t\t\tcontinue\n\t\t}\n\t\torder := &orders[i]\n\t\tif order.ID == payout.OrderID &&',
)
text = text.replace(
    '\t\t\treturn order\n\t\t}\n\t}\n\treturn nil\n}',
    '\t\t\treturn i\n\t\t}\n\t}\n\treturn -1\n}',
)
text = text.replace(
    'func allowedLane(lane string) bool {\n\treturn lane == "D2D" || lane == "LOCKER" || lane == "STORE"\n}',
    'func clean(value string) string {\n\treturn strings.TrimSpace(value)\n}\n\nfunc allowedLane(lane string) bool {\n\tlane = strings.ToUpper(clean(lane))\n\treturn lane == "D2D" || lane == "LOCKER" || lane == "STORE"\n}',
)
path.write_text(text)
PY

/app/scripts/run_batch.sh
test -s /app/out/payout_report.csv
test -s /app/out/payout_summary.json
