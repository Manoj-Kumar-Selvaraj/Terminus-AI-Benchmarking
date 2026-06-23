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
    'out = append(out, Ticket{ID: row[0], Customer: row[1], Amount: amount, Status: row[3], SeatZone: row[4]})',
    'out = append(out, Ticket{ID: clean(row[0]), Customer: clean(row[1]), Amount: amount, Status: strings.ToUpper(clean(row[3])), SeatZone: strings.ToUpper(clean(row[4]))})',
)
text = text.replace(
    'out = append(out, Voucher{TicketID: row[0], Customer: row[1], Amount: amount, SeatZone: row[3]})',
    'out = append(out, Voucher{TicketID: clean(row[0]), Customer: clean(row[1]), Amount: amount, SeatZone: strings.ToUpper(clean(row[3]))})',
)
text = text.replace(
    'summary.MatchedAmountCents -= voucher.Amount',
    'summary.MatchedAmountCents += voucher.Amount',
)
text = text.replace(
    'if len(ticket.ID) >= 8 && len(voucher.TicketID) >= 8 &&\n\t\t\tticket.ID[:8] == voucher.TicketID[:8] &&',
    'if ticket.ID == voucher.TicketID &&',
)
text = text.replace(
    'return seat_zone == "ORCH" || seat_zone == "MEZZ" || seat_zone == "BALC"',
    'return seat_zone == "ORCH" || seat_zone == "MEZZ" || seat_zone == "BALC"',
)
text = text.replace(
    '\tsummary := Summary{}\n\tfor _, voucher := range vouchers {\n\t\tmatch := findMatch(tickets, voucher)',
    '\tsummary := Summary{}\n\tusedTickets := make([]bool, len(tickets))\n\tfor _, voucher := range vouchers {\n\t\tmatchIndex := findMatch(tickets, voucher, usedTickets)\n\t\tvar match *Ticket\n\t\tif matchIndex >= 0 {\n\t\t\tmatch = &tickets[matchIndex]\n\t\t\tusedTickets[matchIndex] = true\n\t\t}',
)
text = text.replace(
    'func findMatch(tickets []Ticket, voucher Voucher) *Ticket {\n\tfor i := range tickets {\n\t\tticket := &tickets[i]\n\t\tif ticket.ID == voucher.TicketID &&',
    'func findMatch(tickets []Ticket, voucher Voucher, used []bool) int {\n\tfor i := range tickets {\n\t\tif used[i] {\n\t\t\tcontinue\n\t\t}\n\t\tticket := &tickets[i]\n\t\tif ticket.ID == voucher.TicketID &&',
)
text = text.replace(
    '\t\t\treturn ticket\n\t\t}\n\t}\n\treturn nil\n}',
    '\t\t\treturn i\n\t\t}\n\t}\n\treturn -1\n}',
)
text = text.replace(
    'func allowedSeatZone(seat_zone string) bool {\n\treturn seat_zone == "ORCH" || seat_zone == "MEZZ" || seat_zone == "BALC"\n}',
    'func clean(value string) string {\n\treturn strings.TrimSpace(value)\n}\n\nfunc allowedSeatZone(seat_zone string) bool {\n\tseat_zone = strings.ToUpper(clean(seat_zone))\n\treturn seat_zone == "ORCH" || seat_zone == "MEZZ" || seat_zone == "BALC"\n}',
)
path.write_text(text)
PY

/app/scripts/run_batch.sh
test -s /app/out/voucher_report.csv
test -s /app/out/voucher_summary.json
