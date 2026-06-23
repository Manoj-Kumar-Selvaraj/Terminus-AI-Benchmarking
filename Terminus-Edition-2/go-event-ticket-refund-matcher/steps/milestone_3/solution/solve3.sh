#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

cd /app

if grep -q 'func detectDatedMode' /app/cmd/reconcile/main.go; then
  /app/scripts/run_batch.sh
  test -s /app/out/refund_report.csv
  test -s /app/out/refund_summary.json
  exit 0
fi

if ! grep -q 'func canonicalTier' /app/cmd/reconcile/main.go; then
  bash "$SCRIPT_DIR/solve2.sh"
fi

python3 <<'PY'
from pathlib import Path

path = Path("/app/cmd/reconcile/main.go")
text = path.read_text()

text = text.replace(
    "type Booking struct {\n\tID       string\n\tCustomer string\n\tAmount   int\n\tStatus   string\n\tTier   string\n}",
    "type Booking struct {\n\tID        string\n\tCustomer  string\n\tAmount    int\n\tStatus    string\n\tTier      string\n\tEventDate string\n}",
)
text = text.replace(
    "type Refund struct {\n\tBookingID string\n\tCustomer  string\n\tAmount    int\n\tTier    string\n}",
    "type Refund struct {\n\tBookingID  string\n\tCustomer   string\n\tAmount     int\n\tTier       string\n\tRefundDate string\n}",
)
text = text.replace(
    "out = append(out, Booking{ID: clean(row[0]), Customer: clean(row[1]), Amount: amount, Status: strings.ToUpper(clean(row[3])), Tier: canonicalTier(row[4])})",
    '''eventDate := ""
\t\tif len(row) > 5 {
\t\t\teventDate = clean(row[5])
\t\t}
\t\tout = append(out, Booking{ID: clean(row[0]), Customer: clean(row[1]), Amount: amount, Status: strings.ToUpper(clean(row[3])), Tier: canonicalTier(row[4]), EventDate: eventDate})''',
)
text = text.replace(
    "out = append(out, Refund{BookingID: clean(row[0]), Customer: clean(row[1]), Amount: amount, Tier: canonicalTier(row[3])})",
    '''refundDate := ""
\t\tif len(row) > 4 {
\t\t\trefundDate = clean(row[4])
\t\t}
\t\tout = append(out, Refund{BookingID: clean(row[0]), Customer: clean(row[1]), Amount: amount, Tier: canonicalTier(row[3]), RefundDate: refundDate})''',
)
text = text.replace(
    "return writeOutputs(bookings, refunds)",
    '''datedMode, err := detectDatedMode()
\tif err != nil {
\t\treturn err
\t}
\topenDates := map[string]bool{}
\tif datedMode {
\t\topenDates, err = loadOpenDates("/app/config/cutoff_calendar.txt")
\t\tif err != nil {
\t\t\treturn err
\t\t}
\t}
\treturn writeOutputs(bookings, refunds, openDates, datedMode)''',
)
text = text.replace(
    "func writeOutputs(bookings []Booking, refunds []Refund) error {",
    "func writeOutputs(bookings []Booking, refunds []Refund, openDates map[string]bool, datedMode bool) error {",
)
text = text.replace(
    "matchIndex := findMatch(bookings, refund, usedBookings)",
    "matchIndex := findMatch(bookings, refund, usedBookings, openDates, datedMode)",
)
start = text.index("func findMatch(")
end = text.index("\nfunc clean(", start)
text = text[:start] + '''func findMatch(bookings []Booking, refund Refund, used []bool, openDates map[string]bool, datedMode bool) int {
\tbestIndex := -1
\tfor i := range bookings {
\t\tif used[i] {
\t\t\tcontinue
\t\t}
\t\tbooking := &bookings[i]
\t\tif datedMode {
\t\t\tif !openDates[refund.RefundDate] ||
\t\t\t\trefund.RefundDate == "" ||
\t\t\t\tbooking.EventDate == "" ||
\t\t\t\trefund.RefundDate > booking.EventDate {
\t\t\t\tcontinue
\t\t\t}
\t\t}
\t\tif booking.ID != refund.BookingID ||
\t\t\tbooking.Customer != refund.Customer ||
\t\t\tbooking.Amount != refund.Amount ||
\t\t\tbooking.Status != "CONFIRMED" ||
\t\t\t!allowedTier(booking.Tier) ||
\t\t\tbooking.Tier != refund.Tier {
\t\t\tcontinue
\t\t}
\t\tif !datedMode {
\t\t\treturn i
\t\t}
\t\tif bestIndex < 0 || booking.EventDate > bookings[bestIndex].EventDate {
\t\t\tbestIndex = i
\t\t} else if booking.EventDate == bookings[bestIndex].EventDate && i < bestIndex {
\t\t\tbestIndex = i
\t\t}
\t}
\treturn bestIndex
}

func detectDatedMode() (bool, error) {
\tbookingRows, err := readRows("/app/data/bookings.csv")
\tif err != nil {
\t\treturn false, err
\t}
\trefundRows, err := readRows("/app/data/refunds.csv")
\tif err != nil {
\t\treturn false, err
\t}
\tbookingHeader, err := readHeader("/app/data/bookings.csv")
\tif err != nil {
\t\treturn false, err
\t}
\trefundHeader, err := readHeader("/app/data/refunds.csv")
\tif err != nil {
\t\treturn false, err
\t}
\t_ = bookingRows
\t_ = refundRows
\treturn contains(bookingHeader, "event_date") && contains(refundHeader, "refund_date"), nil
}

func readHeader(path string) ([]string, error) {
\tf, err := os.Open(path)
\tif err != nil {
\t\treturn nil, err
\t}
\tdefer f.Close()
\treader := csv.NewReader(f)
\treader.FieldsPerRecord = -1
\treturn reader.Read()
}

func contains(values []string, target string) bool {
\tfor _, value := range values {
\t\tif strings.EqualFold(strings.TrimSpace(value), target) {
\t\t\treturn true
\t\t}
\t}
\treturn false
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
test -s /app/out/refund_report.csv
test -s /app/out/refund_summary.json
