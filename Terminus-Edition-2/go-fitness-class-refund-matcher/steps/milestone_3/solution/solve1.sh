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
    'out = append(out, Classpass{ID: row[0], Customer: row[1], Amount: amount, Status: row[3], Studio: row[4]})',
    'out = append(out, Classpass{ID: clean(row[0]), Customer: clean(row[1]), Amount: amount, Status: strings.ToUpper(clean(row[3])), Studio: strings.ToUpper(clean(row[4]))})',
)
text = text.replace(
    'out = append(out, Refund{ClasspassID: row[0], Customer: row[1], Amount: amount, Studio: row[3]})',
    'out = append(out, Refund{ClasspassID: clean(row[0]), Customer: clean(row[1]), Amount: amount, Studio: strings.ToUpper(clean(row[3]))})',
)
text = text.replace(
    'summary.MatchedAmountCents -= refund.Amount',
    'summary.MatchedAmountCents += refund.Amount',
)
text = text.replace(
    'if len(classpass.ID) >= 8 && len(refund.ClasspassID) >= 8 &&\n\t\t\tclasspass.ID[:8] == refund.ClasspassID[:8] &&',
    'if classpass.ID == refund.ClasspassID &&',
)
text = text.replace(
    'return studio == "YOGA" || studio == "SPIN" || studio == "HIIT"',
    'return studio == "YOGA" || studio == "SPIN" || studio == "HIIT"',
)
text = text.replace(
    '\tsummary := Summary{}\n\tfor _, refund := range refunds {\n\t\tmatch := findMatch(classpasses, refund)',
    '\tsummary := Summary{}\n\tusedClasspasss := make([]bool, len(classpasses))\n\tfor _, refund := range refunds {\n\t\tmatchIndex := findMatch(classpasses, refund, usedClasspasss)\n\t\tvar match *Classpass\n\t\tif matchIndex >= 0 {\n\t\t\tmatch = &classpasses[matchIndex]\n\t\t\tusedClasspasss[matchIndex] = true\n\t\t}',
)
text = text.replace(
    'func findMatch(classpasses []Classpass, refund Refund) *Classpass {\n\tfor i := range classpasses {\n\t\tclasspass := &classpasses[i]\n\t\tif classpass.ID == refund.ClasspassID &&',
    'func findMatch(classpasses []Classpass, refund Refund, used []bool) int {\n\tfor i := range classpasses {\n\t\tif used[i] {\n\t\t\tcontinue\n\t\t}\n\t\tclasspass := &classpasses[i]\n\t\tif classpass.ID == refund.ClasspassID &&',
)
text = text.replace(
    '\t\t\treturn classpass\n\t\t}\n\t}\n\treturn nil\n}',
    '\t\t\treturn i\n\t\t}\n\t}\n\treturn -1\n}',
)
text = text.replace(
    'func allowedStudio(studio string) bool {\n\treturn studio == "YOGA" || studio == "SPIN" || studio == "HIIT"\n}',
    'func clean(value string) string {\n\treturn strings.TrimSpace(value)\n}\n\nfunc allowedStudio(studio string) bool {\n\tstudio = strings.ToUpper(clean(studio))\n\treturn studio == "YOGA" || studio == "SPIN" || studio == "HIIT"\n}',
)
path.write_text(text)
PY

/app/scripts/run_batch.sh
test -s /app/out/refund_report.csv
test -s /app/out/refund_summary.json
