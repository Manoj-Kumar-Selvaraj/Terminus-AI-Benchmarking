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
    'out = append(out, Accrual{ID: row[0], Member: row[1], Amount: amount, Status: row[3], Reason: row[4]})',
    'out = append(out, Accrual{ID: clean(row[0]), Member: clean(row[1]), Amount: amount, Status: strings.ToUpper(clean(row[3])), Reason: strings.ToUpper(clean(row[4]))})',
)
text = text.replace(
    'out = append(out, Adjustment{AccrualID: row[0], Member: row[1], Amount: amount, Reason: row[3]})',
    'out = append(out, Adjustment{AccrualID: clean(row[0]), Member: clean(row[1]), Amount: amount, Reason: strings.ToUpper(clean(row[3]))})',
)
text = text.replace(
    'summary.MatchedAmountCents -= adjustment.Amount',
    'summary.MatchedAmountCents += adjustment.Amount',
)
text = text.replace(
    'if len(accrual.ID) >= 8 && len(adjustment.AccrualID) >= 8 &&\n\t\t\taccrual.ID[:8] == adjustment.AccrualID[:8] &&',
    'if accrual.ID == adjustment.AccrualID &&',
)
text = text.replace(
    'return reason == "PURCHASE" || reason == "PROMO"',
    'return reason == "PURCHASE" || reason == "BONUS" || reason == "PROMO"',
)
text = text.replace(
    '\tsummary := Summary{}\n\tfor _, adjustment := range adjustments {\n\t\tmatch := findMatch(accruals, adjustment)',
    '\tsummary := Summary{}\n\tusedAccruals := make([]bool, len(accruals))\n\tfor _, adjustment := range adjustments {\n\t\tmatchIndex := findMatch(accruals, adjustment, usedAccruals)\n\t\tvar match *Accrual\n\t\tif matchIndex >= 0 {\n\t\t\tmatch = &accruals[matchIndex]\n\t\t\tusedAccruals[matchIndex] = true\n\t\t}',
)
text = text.replace(
    'func findMatch(accruals []Accrual, adjustment Adjustment) *Accrual {\n\tfor i := range accruals {\n\t\taccrual := &accruals[i]\n\t\tif accrual.ID == adjustment.AccrualID &&',
    'func findMatch(accruals []Accrual, adjustment Adjustment, used []bool) int {\n\tfor i := range accruals {\n\t\tif used[i] {\n\t\t\tcontinue\n\t\t}\n\t\taccrual := &accruals[i]\n\t\tif accrual.ID == adjustment.AccrualID &&',
)
text = text.replace(
    '\t\t\treturn accrual\n\t\t}\n\t}\n\treturn nil\n}',
    '\t\t\treturn i\n\t\t}\n\t}\n\treturn -1\n}',
)
text = text.replace(
    'func allowedReason(reason string) bool {\n\treturn reason == "PURCHASE" || reason == "BONUS" || reason == "PROMO"\n}',
    'func clean(value string) string {\n\treturn strings.TrimSpace(value)\n}\n\nfunc allowedReason(reason string) bool {\n\treason = strings.ToUpper(clean(reason))\n\treturn reason == "PURCHASE" || reason == "BONUS" || reason == "PROMO"\n}',
)
path.write_text(text)
PY

/app/scripts/run_batch.sh
test -s /app/out/adjustment_report.csv
test -s /app/out/adjustment_summary.json
