#!/usr/bin/env bash
set -euo pipefail

cd /app

if grep -q 'usedBookings' /app/cmd/reconcile/main.go; then
  /app/scripts/run_batch.sh
  test -s /app/out/refund_report.csv
  test -s /app/out/refund_summary.json
  exit 0
fi

python3 <<'PY'
from pathlib import Path

path = Path("/app/cmd/reconcile/main.go")
text = path.read_text()
text = text.replace('"strconv"', '"strconv"\n\t"strings"')
text = text.replace('amount, err := strconv.Atoi(row[2])', 'amount, err := strconv.Atoi(clean(row[2]))')
text = text.replace(
    'out = append(out, Booking{ID: row[0], Customer: row[1], Amount: amount, Status: row[3], Tier: row[4]})',
    'out = append(out, Booking{ID: clean(row[0]), Customer: clean(row[1]), Amount: amount, Status: strings.ToUpper(clean(row[3])), Tier: strings.ToUpper(clean(row[4]))})',
)
text = text.replace(
    'out = append(out, Refund{BookingID: row[0], Customer: row[1], Amount: amount, Tier: row[3]})',
    'out = append(out, Refund{BookingID: clean(row[0]), Customer: clean(row[1]), Amount: amount, Tier: strings.ToUpper(clean(row[3]))})',
)
text = text.replace(
    'summary.MatchedAmountCents -= refund.Amount',
    'summary.MatchedAmountCents += refund.Amount',
)
text = text.replace(
    'if len(booking.ID) >= 8 && len(refund.BookingID) >= 8 &&\n\t\t\tbooking.ID[:8] == refund.BookingID[:8] &&',
    'if booking.ID == refund.BookingID &&',
)
text = text.replace(
    'return tier == "GA" || tier == "VIP" || tier == "COMP"',
    'return tier == "GA" || tier == "VIP" || tier == "COMP"',
)
text = text.replace(
    '\tsummary := Summary{}\n\tfor _, refund := range refunds {\n\t\tmatch := findMatch(bookings, refund)',
    '\tsummary := Summary{}\n\tusedBookings := make([]bool, len(bookings))\n\tfor _, refund := range refunds {\n\t\tmatchIndex := findMatch(bookings, refund, usedBookings)\n\t\tvar match *Booking\n\t\tif matchIndex >= 0 {\n\t\t\tmatch = &bookings[matchIndex]\n\t\t\tusedBookings[matchIndex] = true\n\t\t}',
)
text = text.replace(
    'func findMatch(bookings []Booking, refund Refund) *Booking {\n\tfor i := range bookings {\n\t\tbooking := &bookings[i]\n\t\tif booking.ID == refund.BookingID &&',
    'func findMatch(bookings []Booking, refund Refund, used []bool) int {\n\tfor i := range bookings {\n\t\tif used[i] {\n\t\t\tcontinue\n\t\t}\n\t\tbooking := &bookings[i]\n\t\tif booking.ID == refund.BookingID &&',
)
text = text.replace(
    '\t\t\treturn booking\n\t\t}\n\t}\n\treturn nil\n}',
    '\t\t\treturn i\n\t\t}\n\t}\n\treturn -1\n}',
)
text = text.replace(
    'func allowedTier(tier string) bool {\n\treturn tier == "GA" || tier == "VIP" || tier == "COMP"\n}',
    'func clean(value string) string {\n\treturn strings.TrimSpace(value)\n}\n\nfunc allowedTier(tier string) bool {\n\ttier = strings.ToUpper(clean(tier))\n\treturn tier == "GA" || tier == "VIP" || tier == "COMP"\n}',
)
path.write_text(text)
PY

/app/scripts/run_batch.sh
test -s /app/out/refund_report.csv
test -s /app/out/refund_summary.json
