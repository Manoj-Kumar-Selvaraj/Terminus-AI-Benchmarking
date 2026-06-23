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
    'out = append(out, Sale{ID: row[0], Customer: row[1], Amount: amount, Status: row[3], Format: row[4]})',
    'out = append(out, Sale{ID: clean(row[0]), Customer: clean(row[1]), Amount: amount, Status: strings.ToUpper(clean(row[3])), Format: strings.ToUpper(clean(row[4]))})',
)
text = text.replace(
    'out = append(out, Credit{SaleID: row[0], Customer: row[1], Amount: amount, Format: row[3]})',
    'out = append(out, Credit{SaleID: clean(row[0]), Customer: clean(row[1]), Amount: amount, Format: strings.ToUpper(clean(row[3]))})',
)
text = text.replace(
    'summary.MatchedAmountCents -= credit.Amount',
    'summary.MatchedAmountCents += credit.Amount',
)
text = text.replace(
    'if len(sale.ID) >= 8 && len(credit.SaleID) >= 8 &&\n\t\t\tsale.ID[:8] == credit.SaleID[:8] &&',
    'if sale.ID == credit.SaleID &&',
)
text = text.replace(
    'return format == "LP" || format == "EP" || format == "BOX"',
    'return format == "LP" || format == "EP" || format == "BOX"',
)
text = text.replace(
    '\tsummary := Summary{}\n\tfor _, credit := range credits {\n\t\tmatch := findMatch(sales, credit)',
    '\tsummary := Summary{}\n\tusedSales := make([]bool, len(sales))\n\tfor _, credit := range credits {\n\t\tmatchIndex := findMatch(sales, credit, usedSales)\n\t\tvar match *Sale\n\t\tif matchIndex >= 0 {\n\t\t\tmatch = &sales[matchIndex]\n\t\t\tusedSales[matchIndex] = true\n\t\t}',
)
text = text.replace(
    'func findMatch(sales []Sale, credit Credit) *Sale {\n\tfor i := range sales {\n\t\tsale := &sales[i]\n\t\tif sale.ID == credit.SaleID &&',
    'func findMatch(sales []Sale, credit Credit, used []bool) int {\n\tfor i := range sales {\n\t\tif used[i] {\n\t\t\tcontinue\n\t\t}\n\t\tsale := &sales[i]\n\t\tif sale.ID == credit.SaleID &&',
)
text = text.replace(
    '\t\t\treturn sale\n\t\t}\n\t}\n\treturn nil\n}',
    '\t\t\treturn i\n\t\t}\n\t}\n\treturn -1\n}',
)
text = text.replace(
    'func allowedFormat(format string) bool {\n\treturn format == "LP" || format == "EP" || format == "BOX"\n}',
    'func clean(value string) string {\n\treturn strings.TrimSpace(value)\n}\n\nfunc allowedFormat(format string) bool {\n\tformat = strings.ToUpper(clean(format))\n\treturn format == "LP" || format == "EP" || format == "BOX"\n}',
)
path.write_text(text)
PY

/app/scripts/run_batch.sh
test -s /app/out/credit_report.csv
test -s /app/out/credit_summary.json
