#!/usr/bin/env bash
set -euo pipefail

cd /app

python3 <<'PY'
from pathlib import Path

path = Path("/app/cmd/reconcile/main.go")
text = path.read_text()

text = text.replace(
    "type Booking struct {\n\tID       string\n\tCustomer string\n\tAmount   int\n\tStatus   string\n\tTourType   string\n}",
    "type Booking struct {\n\tID       string\n\tCustomer string\n\tAmount   int\n\tStatus   string\n\tTourType  string\n\tTourDate  string\n}",
)
text = text.replace(
    "type Credit struct {\n\tBookingID string\n\tCustomer  string\n\tAmount    int\n\tTourType    string\n}",
    "type Credit struct {\n\tBookingID     string\n\tCustomer   string\n\tAmount     int\n\tTourType    string\n\tCreditDate string\n}",
)
text = text.replace(
    "out = append(out, Booking{ID: clean(row[0]), Customer: clean(row[1]), Amount: amount, Status: strings.ToUpper(clean(row[3])), TourType: canonicalTourType(row[4])})",
    '''dueDate := ""
\t\tif len(row) > 5 {
\t\t\tdueDate = clean(row[5])
\t\t}
\t\tout = append(out, Booking{ID: clean(row[0]), Customer: clean(row[1]), Amount: amount, Status: strings.ToUpper(clean(row[3])), TourType: canonicalTourType(row[4]), TourDate: dueDate})''',
)
text = text.replace(
    "out = append(out, Credit{BookingID: clean(row[0]), Customer: clean(row[1]), Amount: amount, TourType: canonicalTourType(row[3])})",
    '''creditDate := ""
\t\tif len(row) > 4 {
\t\t\tcreditDate = clean(row[4])
\t\t}
\t\tout = append(out, Credit{BookingID: clean(row[0]), Customer: clean(row[1]), Amount: amount, TourType: canonicalTourType(row[3]), CreditDate: creditDate})''',
)
text = text.replace(
    "return writeOutputs(bookings, credits)",
    '''openDates, err := loadOpenDates("/app/config/cutoff_calendar.txt")
\tif err != nil {
\t\treturn err
\t}
\treturn writeOutputs(bookings, credits, openDates)''',
)
text = text.replace(
    "func writeOutputs(bookings []Booking, credits []Credit) error {",
    "func writeOutputs(bookings []Booking, credits []Credit, openDates map[string]bool) error {",
)
text = text.replace(
    "matchIndex := findMatch(bookings, credit, usedRecords)",
    "matchIndex := findMatch(bookings, credit, usedRecords, openDates)",
)
start = text.index("func findMatch(")
end = text.index("\nfunc clean(", start)
text = text[:start] + '''func findMatch(bookings []Booking, credit Credit, used []bool, openDates map[string]bool) int {
\tbestIndex := -1
\tfor i := range bookings {
\t\tif used[i] {
\t\t\tcontinue
\t\t}
\t\tbooking := &bookings[i]
\t\tif !openDates[credit.CreditDate] ||
\t\t\tcredit.CreditDate == "" ||
\t\t\tbooking.TourDate == "" ||
\t\t\tcredit.CreditDate > booking.TourDate ||
\t\t\tbooking.ID != credit.BookingID ||
\t\t\tbooking.Customer != credit.Customer ||
\t\t\tbooking.Amount != credit.Amount ||
\t\t\tbooking.Status != "SAILED" ||
\t\t\t!allowedTourType(booking.TourType) ||
\t\t\tbooking.TourType != credit.TourType {
\t\t\tcontinue
\t\t}
\t\tif bestIndex < 0 || booking.TourDate > bookings[bestIndex].TourDate {
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
test -s /app/out/credit_report.csv
test -s /app/out/credit_summary.json
