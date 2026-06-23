#!/usr/bin/env bash
set -euo pipefail

cd /app

python3 <<'PY'
from pathlib import Path

path = Path("/app/cmd/reconcile/main.go")
text = path.read_text()
if "ShipDate" in text and "loadOpenDates" in text:
    raise SystemExit(0)

text = text.replace(
    "type Sale struct {\n\tID       string\n\tCustomer string\n\tAmount   int\n\tStatus   string\n\tFormat   string\n}",
    "type Sale struct {\n\tID       string\n\tCustomer string\n\tAmount   int\n\tStatus   string\n\tFormat   string\n\tShipDate string\n}",
)
text = text.replace(
    "type Credit struct {\n\tSaleID string\n\tCustomer  string\n\tAmount    int\n\tFormat    string\n}",
    "type Credit struct {\n\tSaleID     string\n\tCustomer   string\n\tAmount     int\n\tFormat     string\n\tCreditDate string\n}",
)
text = text.replace(
    "out = append(out, Sale{ID: clean(row[0]), Customer: clean(row[1]), Amount: amount, Status: strings.ToUpper(clean(row[3])), Format: canonicalFormat(row[4])})",
    """shipDate := ""
\t\tif len(row) > 5 {
\t\t\tshipDate = clean(row[5])
\t\t}
\t\tout = append(out, Sale{ID: clean(row[0]), Customer: clean(row[1]), Amount: amount, Status: strings.ToUpper(clean(row[3])), Format: canonicalFormat(row[4]), ShipDate: shipDate})""",
)
text = text.replace(
    "out = append(out, Credit{SaleID: clean(row[0]), Customer: clean(row[1]), Amount: amount, Format: canonicalFormat(row[3])})",
    """creditDate := ""
\t\tif len(row) > 4 {
\t\t\tcreditDate = clean(row[4])
\t\t}
\t\tout = append(out, Credit{SaleID: clean(row[0]), Customer: clean(row[1]), Amount: amount, Format: canonicalFormat(row[3]), CreditDate: creditDate})""",
)
text = text.replace(
    "return writeOutputs(sales, credits)",
    """openDates, err := loadOpenDates("/app/config/cutoff_calendar.txt")
\tif err != nil {
\t\treturn err
\t}
\treturn writeOutputs(sales, credits, openDates)""",
)
text = text.replace(
    "func writeOutputs(sales []Sale, credits []Credit) error {",
    "func writeOutputs(sales []Sale, credits []Credit, openDates map[string]bool) error {",
)
text = text.replace(
    "matchIndex := findMatch(sales, credit, usedSales)",
    "matchIndex := findMatch(sales, credit, usedSales, openDates)",
)

start = text.index("func findMatch(")
next_func = len(text)
for marker in ("\nfunc clean(", "\nfunc canonicalFormat(", "\nfunc allowedFormat(", "\nfunc loadOpenDates("):
    pos = text.find(marker, start + 1)
    if pos >= 0:
        next_func = min(next_func, pos)

new_block = '''func findMatch(sales []Sale, credit Credit, used []bool, openDates map[string]bool) int {
\tbestIndex := -1
\tfor i := range sales {
\t\tif used[i] {
\t\t\tcontinue
\t\t}
\t\tsale := &sales[i]
\t\tif !openDates[credit.CreditDate] ||
\t\t\tcredit.CreditDate == "" ||
\t\t\tsale.ShipDate == "" ||
\t\t\tcredit.CreditDate > sale.ShipDate ||
\t\t\tsale.ID != credit.SaleID ||
\t\t\tsale.Customer != credit.Customer ||
\t\t\tsale.Amount != credit.Amount ||
\t\t\tsale.Status != "SHIPPED" ||
\t\t\t!allowedFormat(sale.Format) ||
\t\t\tsale.Format != credit.Format {
\t\t\tcontinue
\t\t}
\t\tif bestIndex < 0 || sale.ShipDate > sales[bestIndex].ShipDate {
\t\t\tbestIndex = i
\t\t}
\t}
\treturn bestIndex
}

func loadOpenDates(path string) (map[string]bool, error) {
\tdata, err := os.ReadFile(path)
\tif err != nil {
\t\treturn nil, err
\t}
\topenDates := map[string]bool{}
\tfor _, line := range strings.Split(string(data), "\\n") {
\t\tfields := strings.Fields(line)
\t\tif len(fields) >= 2 && strings.EqualFold(fields[1], "open") {
\t\t\topenDates[fields[0]] = true
\t\t}
\t}
\treturn openDates, nil
}
'''
text = text[:start] + new_block + text[next_func:]
path.write_text(text)
PY

/app/scripts/run_batch.sh
test -s /app/out/credit_report.csv
test -s /app/out/credit_summary.json
