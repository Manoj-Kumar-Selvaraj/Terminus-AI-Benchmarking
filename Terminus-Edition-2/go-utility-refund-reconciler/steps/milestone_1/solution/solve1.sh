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
    'out = append(out, Bill{ID: row[0], Customer: row[1], Amount: amount, Status: row[3], Channel: row[4]})',
    'out = append(out, Bill{ID: clean(row[0]), Customer: clean(row[1]), Amount: amount, Status: strings.ToUpper(clean(row[3])), Channel: strings.ToUpper(clean(row[4]))})',
)
text = text.replace(
    'out = append(out, Refund{BillID: row[0], Customer: row[1], Amount: amount, Channel: row[3]})',
    'out = append(out, Refund{BillID: clean(row[0]), Customer: clean(row[1]), Amount: amount, Channel: strings.ToUpper(clean(row[3]))})',
)
text = text.replace(
    'summary.MatchedAmountCents -= refund.Amount',
    'summary.MatchedAmountCents += refund.Amount',
)
text = text.replace(
    'if len(bill.ID) >= 8 && len(refund.BillID) >= 8 &&\n\t\t\tbill.ID[:8] == refund.BillID[:8] &&',
    'if bill.ID == refund.BillID &&',
)
text = text.replace(
    'return channel == "ACH" || channel == "WIRE"',
    'return channel == "ACH" || channel == "CARD" || channel == "WIRE"',
)
text = text.replace(
    '\tsummary := Summary{}\n\tfor _, refund := range refunds {\n\t\tmatch := findMatch(bills, refund)',
    '\tsummary := Summary{}\n\tusedBills := make([]bool, len(bills))\n\tfor _, refund := range refunds {\n\t\tmatchIndex := findMatch(bills, refund, usedBills)\n\t\tvar match *Bill\n\t\tif matchIndex >= 0 {\n\t\t\tmatch = &bills[matchIndex]\n\t\t\tusedBills[matchIndex] = true\n\t\t}',
)
text = text.replace(
    'func findMatch(bills []Bill, refund Refund) *Bill {\n\tfor i := range bills {\n\t\tbill := &bills[i]\n\t\tif bill.ID == refund.BillID &&',
    'func findMatch(bills []Bill, refund Refund, used []bool) int {\n\tfor i := range bills {\n\t\tif used[i] {\n\t\t\tcontinue\n\t\t}\n\t\tbill := &bills[i]\n\t\tif bill.ID == refund.BillID &&',
)
text = text.replace(
    '\t\t\treturn bill\n\t\t}\n\t}\n\treturn nil\n}',
    '\t\t\treturn i\n\t\t}\n\t}\n\treturn -1\n}',
)
text = text.replace(
    'func allowedChannel(channel string) bool {\n\treturn channel == "ACH" || channel == "CARD" || channel == "WIRE"\n}',
    'func clean(value string) string {\n\treturn strings.TrimSpace(value)\n}\n\nfunc allowedChannel(channel string) bool {\n\tchannel = strings.ToUpper(clean(channel))\n\treturn channel == "ACH" || channel == "CARD" || channel == "WIRE"\n}',
)
path.write_text(text)
PY

/app/scripts/run_batch.sh
test -s /app/out/refund_report.csv
test -s /app/out/refund_summary.json
