#!/usr/bin/env bash
set -euo pipefail


cd /app

python3 <<'PY'
from pathlib import Path

path = Path("/app/cmd/reconcile/main.go")
text = path.read_text()

text = text.replace(
    "type Rental struct {\n\tID       string\n\tCustomer string\n\tAmount   int\n\tStatus   string\n\tDepot   string\n}",
    "type Rental struct {\n\tID       string\n\tCustomer string\n\tAmount   int\n\tStatus   string\n\tDepot  string\n\tReturnDate  string\n}",
)
text = text.replace(
    "type Deposit struct {\n\tRentalID string\n\tCustomer  string\n\tAmount    int\n\tDepot    string\n}",
    "type Deposit struct {\n\tRentalID     string\n\tCustomer   string\n\tAmount     int\n\tDepot    string\n\tDepositDate string\n}",
)
text = text.replace(
    "out = append(out, Rental{ID: clean(row[0]), Customer: clean(row[1]), Amount: amount, Status: strings.ToUpper(clean(row[3])), Depot: canonicalDepot(row[4])})",
    '''dueDate := ""
\t\tif len(row) > 5 {
\t\t\tdueDate = clean(row[5])
\t\t}
\t\tout = append(out, Rental{ID: clean(row[0]), Customer: clean(row[1]), Amount: amount, Status: strings.ToUpper(clean(row[3])), Depot: canonicalDepot(row[4]), ReturnDate: dueDate})''',
)
text = text.replace(
    "out = append(out, Deposit{RentalID: clean(row[0]), Customer: clean(row[1]), Amount: amount, Depot: canonicalDepot(row[3])})",
    '''depositDate := ""
\t\tif len(row) > 4 {
\t\t\tdepositDate = clean(row[4])
\t\t}
\t\tout = append(out, Deposit{RentalID: clean(row[0]), Customer: clean(row[1]), Amount: amount, Depot: canonicalDepot(row[3]), DepositDate: depositDate})''',
)
text = text.replace(
    "return writeOutputs(rentals, deposits)",
    '''openDates, err := loadOpenDates("/app/config/cutoff_calendar.txt")
\tif err != nil {
\t\treturn err
\t}
\treturn writeOutputs(rentals, deposits, openDates)''',
)
text = text.replace(
    "func writeOutputs(rentals []Rental, deposits []Deposit) error {",
    "func writeOutputs(rentals []Rental, deposits []Deposit, openDates map[string]bool) error {",
)
text = text.replace(
    "matchIndex := findMatch(rentals, deposit, usedRentals)",
    "matchIndex := findMatch(rentals, deposit, usedRentals, openDates)",
)
start = text.index("func findMatch(")
end = text.index("\nfunc clean(", start)
text = text[:start] + '''func findMatch(rentals []Rental, deposit Deposit, used []bool, openDates map[string]bool) int {
\tbestIndex := -1
\tfor i := range rentals {
\t\tif used[i] {
\t\t\tcontinue
\t\t}
\t\trental := &rentals[i]
\t\tif !openDates[deposit.DepositDate] ||
\t\t\tdeposit.DepositDate == "" ||
\t\t\trental.ReturnDate == "" ||
\t\t\tdeposit.DepositDate > rental.ReturnDate ||
\t\t\trental.ID != deposit.RentalID ||
\t\t\trental.Customer != deposit.Customer ||
\t\t\trental.Amount != deposit.Amount ||
\t\t\trental.Status != "RETURNED" ||
\t\t\t!allowedDepot(rental.Depot) ||
\t\t\trental.Depot != deposit.Depot {
\t\t\tcontinue
\t\t}
\t\tif bestIndex < 0 || rental.ReturnDate > rentals[bestIndex].ReturnDate {
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
test -s /app/out/deposit_report.csv
test -s /app/out/deposit_summary.json
