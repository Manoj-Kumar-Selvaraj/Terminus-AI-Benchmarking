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
    'out = append(out, Advance{ID: row[0], Customer: row[1], Amount: amount, Status: row[3], Method: row[4]})',
    'out = append(out, Advance{ID: clean(row[0]), Customer: clean(row[1]), Amount: amount, Status: strings.ToUpper(clean(row[3])), Method: strings.ToUpper(clean(row[4]))})',
)
text = text.replace(
    'out = append(out, Repayment{AdvanceID: row[0], Customer: row[1], Amount: amount, Method: row[3]})',
    'out = append(out, Repayment{AdvanceID: clean(row[0]), Customer: clean(row[1]), Amount: amount, Method: strings.ToUpper(clean(row[3]))})',
)
text = text.replace(
    'summary.MatchedAmountCents -= repayment.Amount',
    'summary.MatchedAmountCents += repayment.Amount',
)
text = text.replace(
    'if len(advance.ID) >= 8 && len(repayment.AdvanceID) >= 8 &&\n\t\t\tadvance.ID[:8] == repayment.AdvanceID[:8] &&',
    'if advance.ID == repayment.AdvanceID &&',
)
text = text.replace(
    'return method == "ACH" || method == "WIRE"',
    'return method == "DIRECT" || method == "PAYROLL" || method == "DEBIT"',
)
text = text.replace(
    '\tsummary := Summary{}\n\tfor _, repayment := range repayments {\n\t\tmatch := findMatch(advances, repayment)',
    '\tsummary := Summary{}\n\tusedAdvances := make([]bool, len(advances))\n\tfor _, repayment := range repayments {\n\t\tmatchIndex := findMatch(advances, repayment, usedAdvances)\n\t\tvar match *Advance\n\t\tif matchIndex >= 0 {\n\t\t\tmatch = &advances[matchIndex]\n\t\t\tusedAdvances[matchIndex] = true\n\t\t}',
)
text = text.replace(
    'func findMatch(advances []Advance, repayment Repayment) *Advance {\n\tfor i := range advances {\n\t\tadvance := &advances[i]\n\t\tif advance.ID == repayment.AdvanceID &&',
    'func findMatch(advances []Advance, repayment Repayment, used []bool) int {\n\tfor i := range advances {\n\t\tif used[i] {\n\t\t\tcontinue\n\t\t}\n\t\tadvance := &advances[i]\n\t\tif advance.ID == repayment.AdvanceID &&',
)
text = text.replace(
    '\t\t\treturn advance\n\t\t}\n\t}\n\treturn nil\n}',
    '\t\t\treturn i\n\t\t}\n\t}\n\treturn -1\n}',
)
text = text.replace(
    'func allowedMethod(method string) bool {\n\treturn method == "DIRECT" || method == "PAYROLL" || method == "DEBIT"\n}',
    'func clean(value string) string {\n\treturn strings.TrimSpace(value)\n}\n\nfunc allowedMethod(method string) bool {\n\tmethod = strings.ToUpper(clean(method))\n\treturn method == "DIRECT" || method == "PAYROLL" || method == "DEBIT"\n}',
)
path.write_text(text)
PY

/app/scripts/run_batch.sh
test -s /app/out/repayment_report.csv
test -s /app/out/repayment_summary.json
