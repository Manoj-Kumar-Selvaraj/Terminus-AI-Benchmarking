#!/usr/bin/env bash
set -euo pipefail

cd /app

python3 <<'PY'
from pathlib import Path

path = Path("/app/cmd/reconcile/main.go")
text = path.read_text()

text = text.replace(
    "type Ticket struct {\n\tID       string\n\tCustomer string\n\tAmount   int\n\tStatus   string\n\tSeatZone   string\n}",
    "type Ticket struct {\n\tID       string\n\tCustomer string\n\tAmount   int\n\tStatus   string\n\tSeatZone  string\n\tShowDate  string\n}",
)
text = text.replace(
    "type Voucher struct {\n\tTicketID string\n\tCustomer  string\n\tAmount    int\n\tSeatZone    string\n}",
    "type Voucher struct {\n\tTicketID     string\n\tCustomer   string\n\tAmount     int\n\tSeatZone    string\n\tVoucherDate string\n}",
)
text = text.replace(
    "out = append(out, Ticket{ID: clean(row[0]), Customer: clean(row[1]), Amount: amount, Status: strings.ToUpper(clean(row[3])), SeatZone: canonicalSeatZone(row[4])})",
    '''dueDate := ""
\t\tif len(row) > 5 {
\t\t\tdueDate = clean(row[5])
\t\t}
\t\tout = append(out, Ticket{ID: clean(row[0]), Customer: clean(row[1]), Amount: amount, Status: strings.ToUpper(clean(row[3])), SeatZone: canonicalSeatZone(row[4]), ShowDate: dueDate})''',
)
text = text.replace(
    "out = append(out, Voucher{TicketID: clean(row[0]), Customer: clean(row[1]), Amount: amount, SeatZone: canonicalSeatZone(row[3])})",
    '''voucherDate := ""
\t\tif len(row) > 4 {
\t\t\tvoucherDate = clean(row[4])
\t\t}
\t\tout = append(out, Voucher{TicketID: clean(row[0]), Customer: clean(row[1]), Amount: amount, SeatZone: canonicalSeatZone(row[3]), VoucherDate: voucherDate})''',
)
text = text.replace(
    "return writeOutputs(tickets, vouchers)",
    '''openDates, err := loadOpenDates("/app/config/cutoff_calendar.txt")
\tif err != nil {
\t\treturn err
\t}
\treturn writeOutputs(tickets, vouchers, openDates)''',
)
text = text.replace(
    "func writeOutputs(tickets []Ticket, vouchers []Voucher) error {",
    "func writeOutputs(tickets []Ticket, vouchers []Voucher, openDates map[string]bool) error {",
)
text = text.replace(
    "matchIndex := findMatch(tickets, voucher, usedTickets)",
    "matchIndex := findMatch(tickets, voucher, usedTickets, openDates)",
)
start = text.index("func findMatch(")
end = text.index("\nfunc clean(", start)
text = text[:start] + '''func findMatch(tickets []Ticket, voucher Voucher, used []bool, openDates map[string]bool) int {
\tbestIndex := -1
\tfor i := range tickets {
\t\tif used[i] {
\t\t\tcontinue
\t\t}
\t\tticket := &tickets[i]
\t\tif !openDates[voucher.VoucherDate] ||
\t\t\tvoucher.VoucherDate == "" ||
\t\t\tticket.ShowDate == "" ||
\t\t\tvoucher.VoucherDate > ticket.ShowDate ||
\t\t\tticket.ID != voucher.TicketID ||
\t\t\tticket.Customer != voucher.Customer ||
\t\t\tticket.Amount != voucher.Amount ||
\t\t\tticket.Status != "ISSUED" ||
\t\t\t!allowedSeatZone(ticket.SeatZone) ||
\t\t\tticket.SeatZone != voucher.SeatZone {
\t\t\tcontinue
\t\t}
\t\tif bestIndex < 0 || ticket.ShowDate > tickets[bestIndex].ShowDate {
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
