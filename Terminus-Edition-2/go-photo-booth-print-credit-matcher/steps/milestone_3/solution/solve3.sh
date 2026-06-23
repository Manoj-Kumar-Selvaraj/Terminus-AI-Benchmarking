#!/usr/bin/env bash
set -euo pipefail

cd /app

python3 <<'PY'
from pathlib import Path

path = Path("/app/cmd/reconcile/main.go")
text = path.read_text()

if "openDates map[string]bool" in text:
    raise SystemExit(0)

if "RideDate  string" not in text:
    import re

    text = re.sub(
        r"type Trip struct \{[^}]+\}",
        "type Trip struct {\n\tID          string\n\tCustomer    string\n\tAmount      int\n\tStatus      string\n\tPassType    string\n\tRideDate    string\n\tHasRideDate bool\n}",
        text,
        count=1,
    )
    text = re.sub(
        r"type Credit struct \{[^}]+\}",
        "type Credit struct {\n\tTripID        string\n\tCustomer      string\n\tAmount        int\n\tPassType      string\n\tCreditDate    string\n\tHasCreditDate bool\n}",
        text,
        count=1,
    )
text = text.replace(
    "out = append(out, Trip{ID: clean(row[0]), Customer: clean(row[1]), Amount: amount, Status: strings.ToUpper(clean(row[3])), PassType: canonicalPassType(row[4])})",
    '''hasRideDate := len(row) > 5
\t\trideDate := ""
\t\tif hasRideDate {
\t\t\trideDate = clean(row[5])
\t\t}
\t\tout = append(out, Trip{ID: clean(row[0]), Customer: clean(row[1]), Amount: amount, Status: strings.ToUpper(clean(row[3])), PassType: canonicalPassType(row[4]), RideDate: rideDate, HasRideDate: hasRideDate})''',
)
text = text.replace(
    "out = append(out, Credit{TripID: clean(row[0]), Customer: clean(row[1]), Amount: amount, PassType: canonicalPassType(row[3])})",
    '''hasCreditDate := len(row) > 4
\t\tcreditDate := ""
\t\tif hasCreditDate {
\t\t\tcreditDate = clean(row[4])
\t\t}
\t\tout = append(out, Credit{TripID: clean(row[0]), Customer: clean(row[1]), Amount: amount, PassType: canonicalPassType(row[3]), CreditDate: creditDate, HasCreditDate: hasCreditDate})''',
)
text = text.replace(
    "return writeOutputs(trips, credits)",
    '''openDates, err := loadOpenDates("/app/config/cutoff_calendar.txt")
\tif err != nil {
\t\treturn err
\t}
\treturn writeOutputs(trips, credits, openDates)''',
)
text = text.replace(
    "func writeOutputs(trips []Trip, credits []Credit) error {",
    "func writeOutputs(trips []Trip, credits []Credit, openDates map[string]bool) error {",
)
text = text.replace(
    "matchIndex := findMatch(trips, credit, usedRecords)",
    "matchIndex := findMatch(trips, credit, usedRecords, openDates)",
)
start = text.index("func findMatch(")
end = text.index("\nfunc clean(", start)
text = text[:start] + '''func findMatch(trips []Trip, credit Credit, used []bool, openDates map[string]bool) int {
\tbestIndex := -1
\tfor i := range trips {
\t\tif used[i] {
\t\t\tcontinue
\t\t}
\t\ttrip := &trips[i]
\t\tif trip.ID != credit.TripID ||
\t\t\ttrip.Customer != credit.Customer ||
\t\t\ttrip.Amount != credit.Amount ||
\t\t\ttrip.Status != "COMPLETED" ||
\t\t\t!allowedPassType(trip.PassType) ||
\t\t\ttrip.PassType != credit.PassType {
\t\t\tcontinue
\t\t}
\t\tdateSchemaActive := credit.HasCreditDate || trip.HasRideDate
\t\tif dateSchemaActive &&
\t\t\t(credit.CreditDate == "" ||
\t\t\t\ttrip.RideDate == "" ||
\t\t\t\t!openDates[credit.CreditDate] ||
\t\t\t\tcredit.CreditDate > trip.RideDate) {
\t\t\tcontinue
\t\t}
\t\tif bestIndex < 0 ||
\t\t\ttrip.RideDate > trips[bestIndex].RideDate ||
\t\t\t(trip.RideDate == trips[bestIndex].RideDate && i < bestIndex) {
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
test -s /app/out/print_credit_report.csv
test -s /app/out/print_credit_summary.json
