#!/usr/bin/env bash
set -euo pipefail

cd /app

python3 <<'PY'
from pathlib import Path

path = Path("/app/cmd/reconcile/main.go")
text = path.read_text()

text = text.replace(
    "type Reservation struct {\n\tID       string\n\tCustomer string\n\tAmount   int\n\tStatus   string\n\tChannel   string\n}",
    "type Reservation struct {\n\tID       string\n\tCustomer string\n\tAmount   int\n\tStatus   string\n\tChannel  string\n\tDueDate  string\n}",
)
text = text.replace(
    "type Credit struct {\n\tReservationID string\n\tCustomer  string\n\tAmount    int\n\tChannel    string\n}",
    "type Credit struct {\n\tReservationID     string\n\tCustomer   string\n\tAmount     int\n\tChannel    string\n\tCreditDate string\n}",
)
text = text.replace(
    "out = append(out, Reservation{ID: clean(row[0]), Customer: clean(row[1]), Amount: amount, Status: strings.ToUpper(clean(row[3])), Channel: canonicalChannel(row[4])})",
    '''dueDate := ""
\t\tif len(row) > 5 {
\t\t\tdueDate = clean(row[5])
\t\t}
\t\tout = append(out, Reservation{ID: clean(row[0]), Customer: clean(row[1]), Amount: amount, Status: strings.ToUpper(clean(row[3])), Channel: canonicalChannel(row[4]), DueDate: dueDate})''',
)
text = text.replace(
    "out = append(out, Credit{ReservationID: clean(row[0]), Customer: clean(row[1]), Amount: amount, Channel: canonicalChannel(row[3])})",
    '''creditDate := ""
\t\tif len(row) > 4 {
\t\t\tcreditDate = clean(row[4])
\t\t}
\t\tout = append(out, Credit{ReservationID: clean(row[0]), Customer: clean(row[1]), Amount: amount, Channel: canonicalChannel(row[3]), CreditDate: creditDate})''',
)
text = text.replace(
    "return writeOutputs(reservations, credits)",
    '''openDates, err := loadOpenDates("/app/config/cutoff_calendar.txt")
\tif err != nil {
\t\treturn err
\t}
\treturn writeOutputs(reservations, credits, openDates)''',
)
text = text.replace(
    "func writeOutputs(reservations []Reservation, credits []Credit) error {",
    "func writeOutputs(reservations []Reservation, credits []Credit, openDates map[string]bool) error {",
)
text = text.replace(
    "matchIndex := findMatch(reservations, credit, usedReservations)",
    "matchIndex := findMatch(reservations, credit, usedReservations, openDates)",
)
start = text.index("func findMatch(")
end = text.index("\nfunc clean(", start)
text = text[:start] + '''func findMatch(reservations []Reservation, credit Credit, used []bool, openDates map[string]bool) int {
\tbestIndex := -1
\tfor i := range reservations {
\t\tif used[i] {
\t\t\tcontinue
\t\t}
\t\treservation := &reservations[i]
\t\tif !openDates[credit.CreditDate] ||
\t\t\tcredit.CreditDate == "" ||
\t\t\treservation.DueDate == "" ||
\t\t\tcredit.CreditDate > reservation.DueDate ||
\t\t\treservation.ID != credit.ReservationID ||
\t\t\treservation.Customer != credit.Customer ||
\t\t\treservation.Amount != credit.Amount ||
\t\t\treservation.Status != "POSTED" ||
\t\t\t!allowedChannel(reservation.Channel) ||
\t\t\treservation.Channel != credit.Channel {
\t\t\tcontinue
\t\t}
\t\tif bestIndex < 0 || reservation.DueDate > reservations[bestIndex].DueDate {
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
