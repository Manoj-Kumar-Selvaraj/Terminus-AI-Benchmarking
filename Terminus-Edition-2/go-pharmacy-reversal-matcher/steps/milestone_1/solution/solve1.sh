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
    'out = append(out, Fill{ID: row[0], Member: row[1], Amount: amount, Status: row[3], Reason: row[4]})',
    'out = append(out, Fill{ID: clean(row[0]), Member: clean(row[1]), Amount: amount, Status: strings.ToUpper(clean(row[3])), Reason: strings.ToUpper(clean(row[4]))})',
)
text = text.replace(
    'out = append(out, Reversal{FillID: row[0], Member: row[1], Amount: amount, Reason: row[3]})',
    'out = append(out, Reversal{FillID: clean(row[0]), Member: clean(row[1]), Amount: amount, Reason: strings.ToUpper(clean(row[3]))})',
)
text = text.replace(
    'summary.MatchedAmountCents -= reversal.Amount',
    'summary.MatchedAmountCents += reversal.Amount',
)
text = text.replace(
    'if len(fill.ID) >= 8 && len(reversal.FillID) >= 8 &&\n\t\t\tfill.ID[:8] == reversal.FillID[:8] &&',
    'if fill.ID == reversal.FillID &&',
)
text = text.replace(
    'return reason == "RX" || reason == "COB"',
    'return reason == "RX" || reason == "COPAY" || reason == "COB"',
)
text = text.replace(
    '\tsummary := Summary{}\n\tfor _, reversal := range reversals {\n\t\tmatch := findMatch(fills, reversal)',
    '\tsummary := Summary{}\n\tusedFills := make([]bool, len(fills))\n\tfor _, reversal := range reversals {\n\t\tmatchIndex := findMatch(fills, reversal, usedFills)\n\t\tvar match *Fill\n\t\tif matchIndex >= 0 {\n\t\t\tmatch = &fills[matchIndex]\n\t\t\tusedFills[matchIndex] = true\n\t\t}',
)
text = text.replace(
    'func findMatch(fills []Fill, reversal Reversal) *Fill {\n\tfor i := range fills {\n\t\tfill := &fills[i]\n\t\tif fill.ID == reversal.FillID &&',
    'func findMatch(fills []Fill, reversal Reversal, used []bool) int {\n\tfor i := range fills {\n\t\tif used[i] {\n\t\t\tcontinue\n\t\t}\n\t\tfill := &fills[i]\n\t\tif fill.ID == reversal.FillID &&',
)
text = text.replace(
    '\t\t\treturn fill\n\t\t}\n\t}\n\treturn nil\n}',
    '\t\t\treturn i\n\t\t}\n\t}\n\treturn -1\n}',
)
text = text.replace(
    'func allowedReason(reason string) bool {\n\treturn reason == "RX" || reason == "COPAY" || reason == "COB"\n}',
    'func clean(value string) string {\n\treturn strings.TrimSpace(value)\n}\n\nfunc allowedReason(reason string) bool {\n\treason = strings.ToUpper(clean(reason))\n\treturn reason == "RX" || reason == "COPAY" || reason == "COB"\n}',
)
path.write_text(text)
PY

/app/scripts/run_batch.sh
test -s /app/out/reversal_report.csv
test -s /app/out/reversal_summary.json
