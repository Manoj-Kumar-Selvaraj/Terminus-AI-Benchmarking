#!/usr/bin/env bash
set -euo pipefail

cd /app

if grep -q 'func loadOpenDates' /app/cmd/reconcile/main.go; then
  /app/scripts/run_batch.sh
  test -s /app/out/tab_adjustment_report.csv
  test -s /app/out/tab_adjustment_summary.json
  exit 0
fi

if ! grep -q 'func canonicalPassType' /app/cmd/reconcile/main.go; then
  if ! grep -q 'usedRecords' /app/cmd/reconcile/main.go; then
python3 <<'PY'
from pathlib import Path

path = Path("/app/cmd/reconcile/main.go")
text = path.read_text()
if '"strings"' not in text:
    text = text.replace('"strconv"', '"strconv"\n\t"strings"')
text = text.replace('amount, err := strconv.Atoi(row[2])', 'amount, err := strconv.Atoi(clean(row[2]))')
text = text.replace(
    'out = append(out, Trip{ID: row[0], Customer: row[1], Amount: amount, Status: row[3], PassType: row[4]})',
    'out = append(out, Trip{ID: clean(row[0]), Customer: clean(row[1]), Amount: amount, Status: strings.ToUpper(clean(row[3])), PassType: strings.ToUpper(clean(row[4]))})',
)
text = text.replace(
    'out = append(out, Credit{TripID: row[0], Customer: row[1], Amount: amount, PassType: row[3]})',
    'out = append(out, Credit{TripID: clean(row[0]), Customer: clean(row[1]), Amount: amount, PassType: strings.ToUpper(clean(row[3]))})',
)
text = text.replace(
    'summary.MatchedAmountCents -= credit.Amount',
    'summary.MatchedAmountCents += credit.Amount',
)
text = text.replace(
    'if len(trip.ID) >= 8 && len(credit.TripID) >= 8 &&\n\t\t\ttrip.ID[:8] == credit.TripID[:8] &&',
    'if trip.ID == credit.TripID &&',
)
text = text.replace(
    '\tsummary := Summary{}\n\tfor _, credit := range credits {\n\t\tmatch := findMatch(trips, credit)',
    '\tsummary := Summary{}\n\tusedRecords := make([]bool, len(trips))\n\tfor _, credit := range credits {\n\t\tmatchIndex := findMatch(trips, credit, usedRecords)\n\t\tvar match *Trip\n\t\tif matchIndex >= 0 {\n\t\t\tmatch = &trips[matchIndex]\n\t\t\tusedRecords[matchIndex] = true\n\t\t}',
)
text = text.replace(
    'func findMatch(trips []Trip, credit Credit) *Trip {\n\tfor i := range trips {\n\t\ttrip := &trips[i]\n\t\tif trip.ID == credit.TripID &&',
    'func findMatch(trips []Trip, credit Credit, used []bool) int {\n\tfor i := range trips {\n\t\tif used[i] {\n\t\t\tcontinue\n\t\t}\n\t\ttrip := &trips[i]\n\t\tif trip.ID == credit.TripID &&',
)
text = text.replace(
    '\t\t\treturn trip\n\t\t}\n\t}\n\treturn nil\n}',
    '\t\t\treturn i\n\t\t}\n\t}\n\treturn -1\n}',
)
text = text.replace(
    'func allowedPassType(pass_type string) bool {\n\treturn pass_type == "PINT" || pass_type == "KEG"\n}',
    'func clean(value string) string {\n\treturn strings.TrimSpace(value)\n}\n\nfunc allowedPassType(pass_type string) bool {\n\tpass_type = strings.ToUpper(clean(pass_type))\n\treturn pass_type == "PINT" || pass_type == "PITCH" || pass_type == "KEG"\n}',
)
text = text.replace(
    'return os.WriteFile("/app/out/credit_summary.json"',
    'return os.WriteFile("/app/out/tab_adjustment_summary.json"',
)
path.write_text(text)
PY
  fi

python3 <<'PY'
from pathlib import Path

path = Path("/app/cmd/reconcile/main.go")
text = path.read_text()

text = text.replace(
    "PassType: strings.ToUpper(clean(row[4]))",
    "PassType: canonicalPassType(row[4])",
)
text = text.replace(
    "PassType: strings.ToUpper(clean(row[3]))",
    "PassType: canonicalPassType(row[3])",
)
text = text.replace(
    'func clean(value string) string {\n\treturn strings.TrimSpace(value)\n}\n\nfunc allowedPassType(pass_type string) bool {\n\tpass_type = strings.ToUpper(clean(pass_type))\n\treturn pass_type == "PINT" || pass_type == "PITCH" || pass_type == "KEG"\n}',
    '''func clean(value string) string {
\treturn strings.TrimSpace(value)
}

func canonicalPassType(pass_type string) string {
\tswitch strings.ToUpper(clean(pass_type)) {
\tcase "PT":
\t\treturn "PINT"
\tcase "PC":
\t\treturn "PITCH"
\tcase "KG":
\t\treturn "KEG"
\tdefault:
\t\treturn strings.ToUpper(clean(pass_type))
\t}
}

func allowedPassType(pass_type string) bool {
\tpass_type = canonicalPassType(pass_type)
\treturn pass_type == "PINT" || pass_type == "PITCH" || pass_type == "KEG"
}''',
)

path.write_text(text)
PY
fi

python3 <<'PY'
from pathlib import Path

path = Path("/app/cmd/reconcile/main.go")
text = path.read_text()

text = text.replace(
    "type Trip struct {\n\tID       string\n\tCustomer string\n\tAmount   int\n\tStatus   string\n\tPassType   string\n}",
    "type Trip struct {\n\tID       string\n\tCustomer string\n\tAmount   int\n\tStatus   string\n\tPassType   string\n\tRideDate  string\n}",
)
text = text.replace(
    "type Credit struct {\n\tTripID string\n\tCustomer  string\n\tAmount    int\n\tPassType    string\n}",
    "type Credit struct {\n\tTripID     string\n\tCustomer   string\n\tAmount     int\n\tPassType   string\n\tCreditDate string\n}",
)
text = text.replace(
    "out = append(out, Trip{ID: clean(row[0]), Customer: clean(row[1]), Amount: amount, Status: strings.ToUpper(clean(row[3])), PassType: canonicalPassType(row[4])})",
    '''tabDate := ""
\t\tif len(row) > 5 {
\t\t\ttabDate = clean(row[5])
\t\t}
\t\tout = append(out, Trip{ID: clean(row[0]), Customer: clean(row[1]), Amount: amount, Status: strings.ToUpper(clean(row[3])), PassType: canonicalPassType(row[4]), RideDate: tabDate})''',
)
text = text.replace(
    "out = append(out, Credit{TripID: clean(row[0]), Customer: clean(row[1]), Amount: amount, PassType: canonicalPassType(row[3])})",
    '''adjustDate := ""
\t\tif len(row) > 4 {
\t\t\tadjustDate = clean(row[4])
\t\t}
\t\tout = append(out, Credit{TripID: clean(row[0]), Customer: clean(row[1]), Amount: amount, PassType: canonicalPassType(row[3]), CreditDate: adjustDate})''',
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
\t\ttrip := &trips[i]
\t\tif used[i] {
\t\t\tcontinue
\t\t}
\t\tdateGated := credit.CreditDate != "" || trip.RideDate != ""
\t\tif dateGated {
\t\t\tif !validDate(credit.CreditDate) ||
\t\t\t\t!validDate(trip.RideDate) ||
\t\t\t\t!openDates[credit.CreditDate] ||
\t\t\t\tcredit.CreditDate == "" ||
\t\t\t\ttrip.RideDate == "" ||
\t\t\t\tcredit.CreditDate > trip.RideDate {
\t\t\t\tcontinue
\t\t\t}
\t\t}
\t\tif trip.ID != credit.TripID ||
\t\t\ttrip.Customer != credit.Customer ||
\t\t\ttrip.Amount != credit.Amount ||
\t\t\ttrip.Status != "COMPLETED" ||
\t\t\t!allowedPassType(trip.PassType) ||
\t\t\ttrip.PassType != credit.PassType {
\t\t\tcontinue
\t\t}
\t\tif credit.CreditDate == "" && trip.RideDate == "" {
\t\t\treturn i
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
\t\tif len(fields) >= 2 && validDate(fields[0]) && strings.EqualFold(fields[1], "open") {
\t\t\topenDates[fields[0]] = true
\t\t}
\t}
\treturn openDates, nil
}

func validDate(value string) bool {
\tif len(value) != 10 || value[4] != '-' || value[7] != '-' {
\t\treturn false
\t}
\tfor i, r := range value {
\t\tif i == 4 || i == 7 {
\t\t\tcontinue
\t\t}
\t\tif r < '0' || r > '9' {
\t\t\treturn false
\t\t}
\t}
\tmonth := value[5:7]
\tday := value[8:10]
\treturn month >= "01" && month <= "12" && day >= "01" && day <= "31"
}
''' + text[end:]

path.write_text(text)
PY

/app/scripts/run_batch.sh
test -s /app/out/tab_adjustment_report.csv
test -s /app/out/tab_adjustment_summary.json
