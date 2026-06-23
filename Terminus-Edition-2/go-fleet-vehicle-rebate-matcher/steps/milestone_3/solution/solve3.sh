#!/usr/bin/env bash
set -euo pipefail

cd /app

python3 <<'PY'
from pathlib import Path

path = Path("/app/cmd/reconcile/main.go")
text = path.read_text()

text = text.replace(
    "type Vehicle struct {\n\tID       string\n\tCustomer string\n\tAmount   int\n\tStatus   string\n\tChannel   string\n}",
    "type Vehicle struct {\n\tID       string\n\tCustomer string\n\tAmount   int\n\tStatus   string\n\tChannel  string\n\tDueDate  string\n}",
)
text = text.replace(
    "type Rebate struct {\n\tVehicleID string\n\tCustomer  string\n\tAmount    int\n\tChannel    string\n}",
    "type Rebate struct {\n\tVehicleID     string\n\tCustomer   string\n\tAmount     int\n\tChannel    string\n\tRebateDate string\n}",
)
text = text.replace(
    "out = append(out, Vehicle{ID: clean(row[0]), Customer: clean(row[1]), Amount: amount, Status: strings.ToUpper(clean(row[3])), Channel: canonicalChannel(row[4])})",
    '''dueDate := ""
\t\tif len(row) > 5 {
\t\t\tdueDate = clean(row[5])
\t\t}
\t\tout = append(out, Vehicle{ID: clean(row[0]), Customer: clean(row[1]), Amount: amount, Status: strings.ToUpper(clean(row[3])), Channel: canonicalChannel(row[4]), DueDate: dueDate})''',
)
text = text.replace(
    "out = append(out, Rebate{VehicleID: clean(row[0]), Customer: clean(row[1]), Amount: amount, Channel: canonicalChannel(row[3])})",
    '''rebateDate := ""
\t\tif len(row) > 4 {
\t\t\trebateDate = clean(row[4])
\t\t}
\t\tout = append(out, Rebate{VehicleID: clean(row[0]), Customer: clean(row[1]), Amount: amount, Channel: canonicalChannel(row[3]), RebateDate: rebateDate})''',
)
text = text.replace(
    "return writeOutputs(vehicles, rebates)",
    '''openDates, err := loadOpenDates("/app/config/cutoff_calendar.txt")
\tif err != nil {
\t\treturn err
\t}
\treturn writeOutputs(vehicles, rebates, openDates)''',
)
text = text.replace(
    "func writeOutputs(vehicles []Vehicle, rebates []Rebate) error {",
    "func writeOutputs(vehicles []Vehicle, rebates []Rebate, openDates map[string]bool) error {",
)
text = text.replace(
    "matchIndex := findMatch(vehicles, rebate, usedVehicles)",
    "matchIndex := findMatch(vehicles, rebate, usedVehicles, openDates)",
)
start = text.index("func findMatch(")
end = text.index("\nfunc clean(", start)
text = text[:start] + '''func findMatch(vehicles []Vehicle, rebate Rebate, used []bool, openDates map[string]bool) int {
\tbestIndex := -1
\tfor i := range vehicles {
\t\tif used[i] {
\t\t\tcontinue
\t\t}
\t\tvehicle := &vehicles[i]
\t\tif !openDates[rebate.RebateDate] ||
\t\t\trebate.RebateDate == "" ||
\t\t\tvehicle.DueDate == "" ||
\t\t\trebate.RebateDate > vehicle.DueDate ||
\t\t\tvehicle.ID != rebate.VehicleID ||
\t\t\tvehicle.Customer != rebate.Customer ||
\t\t\tvehicle.Amount != rebate.Amount ||
\t\t\tvehicle.Status != "POSTED" ||
\t\t\t!allowedChannel(vehicle.Channel) ||
\t\t\tvehicle.Channel != rebate.Channel {
\t\t\tcontinue
\t\t}
\t\tif bestIndex < 0 || vehicle.DueDate > vehicles[bestIndex].DueDate {
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
test -s /app/out/rebate_report.csv
test -s /app/out/rebate_summary.json
