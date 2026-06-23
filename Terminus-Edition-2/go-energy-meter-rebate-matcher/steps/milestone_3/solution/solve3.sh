#!/usr/bin/env bash
set -euo pipefail

cd /app

python3 <<'PY'
from pathlib import Path

path = Path("/app/cmd/reconcile/main.go")
text = path.read_text()

text = text.replace(
    "type Meter struct {\n\tID       string\n\tCustomer string\n\tAmount   int\n\tStatus   string\n\tChannel   string\n}",
    "type Meter struct {\n\tID       string\n\tCustomer string\n\tAmount   int\n\tStatus   string\n\tChannel  string\n\tDueDate  string\n}",
)
text = text.replace(
    "type Rebate struct {\n\tMeterID string\n\tCustomer  string\n\tAmount    int\n\tChannel    string\n}",
    "type Rebate struct {\n\tMeterID     string\n\tCustomer   string\n\tAmount     int\n\tChannel    string\n\tRebateDate string\n}",
)
text = text.replace(
    "out = append(out, Meter{ID: clean(row[0]), Customer: clean(row[1]), Amount: amount, Status: strings.ToUpper(clean(row[3])), Channel: canonicalChannel(row[4])})",
    '''dueDate := ""
\t\tif len(row) > 5 {
\t\t\tdueDate = clean(row[5])
\t\t}
\t\tout = append(out, Meter{ID: clean(row[0]), Customer: clean(row[1]), Amount: amount, Status: strings.ToUpper(clean(row[3])), Channel: canonicalChannel(row[4]), DueDate: dueDate})''',
)
text = text.replace(
    "out = append(out, Rebate{MeterID: clean(row[0]), Customer: clean(row[1]), Amount: amount, Channel: canonicalChannel(row[3])})",
    '''rebateDate := ""
\t\tif len(row) > 4 {
\t\t\trebateDate = clean(row[4])
\t\t}
\t\tout = append(out, Rebate{MeterID: clean(row[0]), Customer: clean(row[1]), Amount: amount, Channel: canonicalChannel(row[3]), RebateDate: rebateDate})''',
)
text = text.replace(
    "return writeOutputs(meters, rebates)",
    '''openDates, err := loadOpenDates("/app/config/cutoff_calendar.txt")
\tif err != nil {
\t\treturn err
\t}
\treturn writeOutputs(meters, rebates, openDates)''',
)
text = text.replace(
    "func writeOutputs(meters []Meter, rebates []Rebate) error {",
    "func writeOutputs(meters []Meter, rebates []Rebate, openDates map[string]bool) error {",
)
text = text.replace(
    "matchIndex := findMatch(meters, rebate, usedMeters)",
    "matchIndex := findMatch(meters, rebate, usedMeters, openDates)",
)
start = text.index("func findMatch(")
end = text.index("\nfunc clean(", start)
text = text[:start] + '''func findMatch(meters []Meter, rebate Rebate, used []bool, openDates map[string]bool) int {
\tbestIndex := -1
\tfor i := range meters {
\t\tif used[i] {
\t\t\tcontinue
\t\t}
\t\tmeter := &meters[i]
\t\tif !openDates[rebate.RebateDate] ||
\t\t\trebate.RebateDate == "" ||
\t\t\tmeter.DueDate == "" ||
\t\t\trebate.RebateDate > meter.DueDate ||
\t\t\tmeter.ID != rebate.MeterID ||
\t\t\tmeter.Customer != rebate.Customer ||
\t\t\tmeter.Amount != rebate.Amount ||
\t\t\tmeter.Status != "POSTED" ||
\t\t\t!allowedChannel(meter.Channel) ||
\t\t\tmeter.Channel != rebate.Channel {
\t\t\tcontinue
\t\t}
\t\tif bestIndex < 0 || meter.DueDate > meters[bestIndex].DueDate {
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
