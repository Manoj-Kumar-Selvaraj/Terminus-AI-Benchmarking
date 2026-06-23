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
    'out = append(out, Order{ID: row[0], Customer: row[1], Amount: amount, Status: row[3], Channel: row[4]})',
    'out = append(out, Order{ID: clean(row[0]), Customer: clean(row[1]), Amount: amount, Status: strings.ToUpper(clean(row[3])), Channel: strings.ToUpper(clean(row[4]))})',
)
text = text.replace(
    'out = append(out, Voucher{OrderID: row[0], Customer: row[1], Amount: amount, Channel: row[3]})',
    'out = append(out, Voucher{OrderID: clean(row[0]), Customer: clean(row[1]), Amount: amount, Channel: strings.ToUpper(clean(row[3]))})',
)
text = text.replace(
    'summary.MatchedAmountCents -= voucher.Amount',
    'summary.MatchedAmountCents += voucher.Amount',
)
text = text.replace(
    'if len(order.ID) >= 8 && len(voucher.OrderID) >= 8 &&\n\t\t\torder.ID[:8] == voucher.OrderID[:8] &&',
    'if order.ID == voucher.OrderID &&',
)
text = text.replace(
    'return channel == "ACH" || channel == "WIRE"',
    'return channel == "ACH" || channel == "CARD" || channel == "WIRE"',
)
text = text.replace(
    '\tsummary := Summary{}\n\tfor _, voucher := range vouchers {\n\t\tmatch := findMatch(orders, voucher)',
    '\tsummary := Summary{}\n\tusedOrders := make([]bool, len(orders))\n\tfor _, voucher := range vouchers {\n\t\tmatchIndex := findMatch(orders, voucher, usedOrders)\n\t\tvar match *Order\n\t\tif matchIndex >= 0 {\n\t\t\tmatch = &orders[matchIndex]\n\t\t\tusedOrders[matchIndex] = true\n\t\t}',
)
text = text.replace(
    'func findMatch(orders []Order, voucher Voucher) *Order {\n\tfor i := range orders {\n\t\torder := &orders[i]\n\t\tif order.ID == voucher.OrderID &&',
    'func findMatch(orders []Order, voucher Voucher, used []bool) int {\n\tfor i := range orders {\n\t\tif used[i] {\n\t\t\tcontinue\n\t\t}\n\t\torder := &orders[i]\n\t\tif order.ID == voucher.OrderID &&',
)
text = text.replace(
    '\t\t\treturn order\n\t\t}\n\t}\n\treturn nil\n}',
    '\t\t\treturn i\n\t\t}\n\t}\n\treturn -1\n}',
)
text = text.replace(
    'func allowedChannel(channel string) bool {\n\treturn channel == "ACH" || channel == "CARD" || channel == "WIRE"\n}',
    'func clean(value string) string {\n\treturn strings.TrimSpace(value)\n}\n\nfunc allowedChannel(channel string) bool {\n\tchannel = strings.ToUpper(clean(channel))\n\treturn channel == "ACH" || channel == "CARD" || channel == "WIRE"\n}',
)
path.write_text(text)
PY

/app/scripts/run_batch.sh
test -s /app/out/voucher_report.csv
test -s /app/out/voucher_summary.json
