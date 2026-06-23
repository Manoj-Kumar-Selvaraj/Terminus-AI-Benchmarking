#!/usr/bin/env bash
set -euo pipefail

cd /app

python3 <<'PY'
from pathlib import Path

path = Path("/app/cmd/reconcile/main.go")
text = path.read_text()

text = text.replace(
    "type Order struct {\n\tID       string\n\tCustomer string\n\tAmount   int\n\tStatus   string\n\tChannel   string\n}",
    "type Order struct {\n\tID       string\n\tCustomer string\n\tAmount   int\n\tStatus   string\n\tChannel  string\n\tDueDate  string\n}",
)
text = text.replace(
    "type Voucher struct {\n\tOrderID string\n\tCustomer  string\n\tAmount    int\n\tChannel    string\n}",
    "type Voucher struct {\n\tOrderID     string\n\tCustomer   string\n\tAmount     int\n\tChannel    string\n\tVoucherDate string\n}",
)
text = text.replace(
    "out = append(out, Order{ID: clean(row[0]), Customer: clean(row[1]), Amount: amount, Status: strings.ToUpper(clean(row[3])), Channel: canonicalChannel(row[4])})",
    '''dueDate := ""
\t\tif len(row) > 5 {
\t\t\tdueDate = clean(row[5])
\t\t}
\t\tout = append(out, Order{ID: clean(row[0]), Customer: clean(row[1]), Amount: amount, Status: strings.ToUpper(clean(row[3])), Channel: canonicalChannel(row[4]), DueDate: dueDate})''',
)
text = text.replace(
    "out = append(out, Voucher{OrderID: clean(row[0]), Customer: clean(row[1]), Amount: amount, Channel: canonicalChannel(row[3])})",
    '''voucherDate := ""
\t\tif len(row) > 4 {
\t\t\tvoucherDate = clean(row[4])
\t\t}
\t\tout = append(out, Voucher{OrderID: clean(row[0]), Customer: clean(row[1]), Amount: amount, Channel: canonicalChannel(row[3]), VoucherDate: voucherDate})''',
)
text = text.replace(
    "return writeOutputs(orders, vouchers)",
    '''openDates, err := loadOpenDates("/app/config/cutoff_calendar.txt")
\tif err != nil {
\t\treturn err
\t}
\treturn writeOutputs(orders, vouchers, openDates)''',
)
text = text.replace(
    "func writeOutputs(orders []Order, vouchers []Voucher) error {",
    "func writeOutputs(orders []Order, vouchers []Voucher, openDates map[string]bool) error {",
)
text = text.replace(
    "matchIndex := findMatch(orders, voucher, usedOrders)",
    "matchIndex := findMatch(orders, voucher, usedOrders, openDates)",
)
start = text.index("func findMatch(")
end = text.index("\nfunc clean(", start)
text = text[:start] + '''func findMatch(orders []Order, voucher Voucher, used []bool, openDates map[string]bool) int {
\tbestIndex := -1
\tfor i := range orders {
\t\tif used[i] {
\t\t\tcontinue
\t\t}
\t\torder := &orders[i]
\t\tif !openDates[voucher.VoucherDate] ||
\t\t\tvoucher.VoucherDate == "" ||
\t\t\torder.DueDate == "" ||
\t\t\tvoucher.VoucherDate > order.DueDate ||
\t\t\torder.ID != voucher.OrderID ||
\t\t\torder.Customer != voucher.Customer ||
\t\t\torder.Amount != voucher.Amount ||
\t\t\torder.Status != "POSTED" ||
\t\t\t!allowedChannel(order.Channel) ||
\t\t\torder.Channel != voucher.Channel {
\t\t\tcontinue
\t\t}
\t\tif bestIndex < 0 || order.DueDate > orders[bestIndex].DueDate {
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
''' + text[end:]

path.write_text(text)
PY

/app/scripts/run_batch.sh
test -s /app/out/voucher_report.csv
test -s /app/out/voucher_summary.json
