#!/usr/bin/env bash
set -euo pipefail

cd /app

python3 <<'PY'
from pathlib import Path

path = Path("/app/cmd/reconcile/main.go")
text = path.read_text()
if '"strings"' not in text:
    text = text.replace('"strconv"', '"strconv"\n\t"strings"')
text = text.replace('amount, err := strconv.Atoi(row[2])', 'amount, err := strconv.Atoi(clean(row[2]))')
text = text.replace(
    'out = append(out, Stall{ID: row[0], Customer: row[1], Amount: amount, Status: row[3], StallType: row[4]})',
    'out = append(out, Stall{ID: clean(row[0]), Customer: clean(row[1]), Amount: amount, Status: strings.ToUpper(clean(row[3])), StallType: strings.ToUpper(clean(row[4]))})',
)
text = text.replace(
    'out = append(out, Refund{StallID: row[0], Customer: row[1], Amount: amount, StallType: row[3]})',
    'out = append(out, Refund{StallID: clean(row[0]), Customer: clean(row[1]), Amount: amount, StallType: strings.ToUpper(clean(row[3]))})',
)
text = text.replace(
    'summary.MatchedAmountCents -= refund.Amount',
    'summary.MatchedAmountCents += refund.Amount',
)
text = text.replace(
    'if len(stall.ID) >= 8 && len(refund.StallID) >= 8 &&\n\t\t\tstall.ID[:8] == refund.StallID[:8] &&',
    'if stall.ID == refund.StallID &&',
)
text = text.replace(
    '\tsummary := Summary{}\n\tfor _, refund := range refunds {\n\t\tmatch := findMatch(stalls, refund)',
    '\tsummary := Summary{}\n\tusedRecords := make([]bool, len(stalls))\n\tfor _, refund := range refunds {\n\t\tmatchIndex := findMatch(stalls, refund, usedRecords)\n\t\tvar match *Stall\n\t\tif matchIndex >= 0 {\n\t\t\tmatch = &stalls[matchIndex]\n\t\t\tusedRecords[matchIndex] = true\n\t\t}',
)
text = text.replace(
    'func findMatch(stalls []Stall, refund Refund) *Stall {\n\tfor i := range stalls {\n\t\tstall := &stalls[i]\n\t\tif stall.ID == refund.StallID &&',
    'func findMatch(stalls []Stall, refund Refund, used []bool) int {\n\tfor i := range stalls {\n\t\tif used[i] {\n\t\t\tcontinue\n\t\t}\n\t\tstall := &stalls[i]\n\t\tif stall.ID == refund.StallID &&',
)
text = text.replace(
    '\t\t\treturn stall\n\t\t}\n\t}\n\treturn nil\n}',
    '\t\t\treturn i\n\t\t}\n\t}\n\treturn -1\n}',
)
text = text.replace(
    'func allowedStallType(stallType string) bool {\n\tstallType = strings.ToUpper(strings.TrimSpace(stallType))\n\treturn stallType == "PRODUCE" || stallType == "CRAFT"\n}',
    'func clean(value string) string {\n\treturn strings.TrimSpace(value)\n}\n\nfunc allowedStallType(stallType string) bool {\n\tstallType = strings.ToUpper(clean(stallType))\n\treturn stallType == "PRODUCE" || stallType == "CRAFT" || stallType == "FOOD"\n}',
)
text = text.replace(
    'stallType = match.StallType',
    'stallType = refund.StallType',
)
path.write_text(text)
PY

/app/scripts/run_batch.sh
test -s /app/out/refund_report.csv
test -s /app/out/refund_summary.json
