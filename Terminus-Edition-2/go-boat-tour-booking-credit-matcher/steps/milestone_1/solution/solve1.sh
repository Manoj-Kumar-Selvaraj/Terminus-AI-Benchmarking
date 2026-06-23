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
    'out = append(out, Booking{ID: row[0], Customer: row[1], Amount: amount, Status: row[3], TourType: row[4]})',
    'out = append(out, Booking{ID: clean(row[0]), Customer: clean(row[1]), Amount: amount, Status: strings.ToUpper(clean(row[3])), TourType: strings.ToUpper(clean(row[4]))})',
)
text = text.replace(
    'out = append(out, Credit{BookingID: row[0], Customer: row[1], Amount: amount, TourType: row[3]})',
    'out = append(out, Credit{BookingID: clean(row[0]), Customer: clean(row[1]), Amount: amount, TourType: strings.ToUpper(clean(row[3]))})',
)
text = text.replace(
    'summary.MatchedAmountCents -= credit.Amount',
    'summary.MatchedAmountCents += credit.Amount',
)
text = text.replace(
    'if len(booking.ID) >= 8 && len(credit.BookingID) >= 8 &&\n\t\t\tbooking.ID[:8] == credit.BookingID[:8] &&',
    'if booking.ID == credit.BookingID &&',
)
text = text.replace(
    'return tour_type == "HARBOR" || tour_type == "SUNSET" || tour_type == "WHALE"',
    'return tour_type == "HARBOR" || tour_type == "SUNSET" || tour_type == "WHALE"',
)
text = text.replace(
    '\tsummary := Summary{}\n\tfor _, credit := range credits {\n\t\tmatch := findMatch(bookings, credit)',
    '\tsummary := Summary{}\n\tusedRecords := make([]bool, len(bookings))\n\tfor _, credit := range credits {\n\t\tmatchIndex := findMatch(bookings, credit, usedRecords)\n\t\tvar match *Booking\n\t\tif matchIndex >= 0 {\n\t\t\tmatch = &bookings[matchIndex]\n\t\t\tusedRecords[matchIndex] = true\n\t\t}',
)
text = text.replace(
    'func findMatch(bookings []Booking, credit Credit) *Booking {\n\tfor i := range bookings {\n\t\tbooking := &bookings[i]\n\t\tif booking.ID == credit.BookingID &&',
    'func findMatch(bookings []Booking, credit Credit, used []bool) int {\n\tfor i := range bookings {\n\t\tif used[i] {\n\t\t\tcontinue\n\t\t}\n\t\tbooking := &bookings[i]\n\t\tif booking.ID == credit.BookingID &&',
)
text = text.replace(
    '\t\t\treturn booking\n\t\t}\n\t}\n\treturn nil\n}',
    '\t\t\treturn i\n\t\t}\n\t}\n\treturn -1\n}',
)
text = text.replace(
    'func allowedTourType(tour_type string) bool {\n\treturn tour_type == "HARBOR" || tour_type == "SUNSET" || tour_type == "WHALE"\n}',
    'func clean(value string) string {\n\treturn strings.TrimSpace(value)\n}\n\nfunc allowedTourType(tour_type string) bool {\n\ttour_type = strings.ToUpper(clean(tour_type))\n\treturn tour_type == "HARBOR" || tour_type == "SUNSET" || tour_type == "WHALE"\n}',
)
path.write_text(text)
PY

/app/scripts/run_batch.sh
test -s /app/out/credit_report.csv
test -s /app/out/credit_summary.json
