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
    'out = append(out, Charge{ID: row[0], Customer: row[1], Amount: amount, Status: row[3], Mode: row[4]})',
    'out = append(out, Charge{ID: clean(row[0]), Customer: clean(row[1]), Amount: amount, Status: strings.ToUpper(clean(row[3])), Mode: strings.ToUpper(clean(row[4]))})',
)
text = text.replace(
    'out = append(out, Credit{ChargeID: row[0], Customer: row[1], Amount: amount, Mode: row[3]})',
    'out = append(out, Credit{ChargeID: clean(row[0]), Customer: clean(row[1]), Amount: amount, Mode: strings.ToUpper(clean(row[3]))})',
)
text = text.replace(
    'summary.MatchedAmountCents -= credit.Amount',
    'summary.MatchedAmountCents += credit.Amount',
)
text = text.replace(
    'if len(charge.ID) >= 8 && len(credit.ChargeID) >= 8 &&\n\t\t\tcharge.ID[:8] == credit.ChargeID[:8] &&',
    'if charge.ID == credit.ChargeID &&',
)
text = text.replace(
    'return mode == "LTL" || mode == "FTL" || mode == "RAIL"',
    'return mode == "LTL" || mode == "FTL" || mode == "RAIL"',
)
text = text.replace(
    '\tsummary := Summary{}\n\tfor _, credit := range credits {\n\t\tmatch := findMatch(charges, credit)',
    '\tsummary := Summary{}\n\tusedCharges := make([]bool, len(charges))\n\tfor _, credit := range credits {\n\t\tmatchIndex := findMatch(charges, credit, usedCharges)\n\t\tvar match *Charge\n\t\tif matchIndex >= 0 {\n\t\t\tmatch = &charges[matchIndex]\n\t\t\tusedCharges[matchIndex] = true\n\t\t}',
)
text = text.replace(
    'func findMatch(charges []Charge, credit Credit) *Charge {\n\tfor i := range charges {\n\t\tcharge := &charges[i]\n\t\tif charge.ID == credit.ChargeID &&',
    'func findMatch(charges []Charge, credit Credit, used []bool) int {\n\tfor i := range charges {\n\t\tif used[i] {\n\t\t\tcontinue\n\t\t}\n\t\tcharge := &charges[i]\n\t\tif charge.ID == credit.ChargeID &&',
)
text = text.replace(
    '\t\t\treturn charge\n\t\t}\n\t}\n\treturn nil\n}',
    '\t\t\treturn i\n\t\t}\n\t}\n\treturn -1\n}',
)
text = text.replace(
    'func allowedMode(mode string) bool {\n\treturn mode == "LTL" || mode == "FTL" || mode == "RAIL"\n}',
    'func clean(value string) string {\n\treturn strings.TrimSpace(value)\n}\n\nfunc allowedMode(mode string) bool {\n\tmode = strings.ToUpper(clean(mode))\n\treturn mode == "LTL" || mode == "FTL" || mode == "RAIL"\n}',
)
path.write_text(text)
PY

/app/scripts/run_batch.sh
test -s /app/out/credit_report.csv
test -s /app/out/credit_summary.json
