#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
bash "$SCRIPT_DIR/solve2.sh"

cd /app

python3 <<'PY'
from pathlib import Path

path = Path("/app/cmd/reconcile/main.go")
text = path.read_text()

text = text.replace(
    "type Classpass struct {\n\tID       string\n\tCustomer string\n\tAmount   int\n\tStatus   string\n\tStudio   string\n}",
    "type Classpass struct {\n\tID       string\n\tCustomer string\n\tAmount   int\n\tStatus   string\n\tStudio  string\n\tClassDate  string\n}",
)
text = text.replace(
    "type Refund struct {\n\tClasspassID string\n\tCustomer  string\n\tAmount    int\n\tStudio    string\n}",
    "type Refund struct {\n\tClasspassID     string\n\tCustomer   string\n\tAmount     int\n\tStudio    string\n\tRefundDate string\n}",
)
text = text.replace(
    "out = append(out, Classpass{ID: clean(row[0]), Customer: clean(row[1]), Amount: amount, Status: strings.ToUpper(clean(row[3])), Studio: canonicalStudio(row[4])})",
    '''dueDate := ""
\t\tif len(row) > 5 {
\t\t\tdueDate = clean(row[5])
\t\t}
\t\tout = append(out, Classpass{ID: clean(row[0]), Customer: clean(row[1]), Amount: amount, Status: strings.ToUpper(clean(row[3])), Studio: canonicalStudio(row[4]), ClassDate: dueDate})''',
)
text = text.replace(
    "out = append(out, Refund{ClasspassID: clean(row[0]), Customer: clean(row[1]), Amount: amount, Studio: canonicalStudio(row[3])})",
    '''refundDate := ""
\t\tif len(row) > 4 {
\t\t\trefundDate = clean(row[4])
\t\t}
\t\tout = append(out, Refund{ClasspassID: clean(row[0]), Customer: clean(row[1]), Amount: amount, Studio: canonicalStudio(row[3]), RefundDate: refundDate})''',
)
text = text.replace(
    "return writeOutputs(classpasses, refunds)",
    '''openDates, err := loadOpenDates("/app/config/cutoff_calendar.txt")
\tif err != nil {
\t\treturn err
\t}
\treturn writeOutputs(classpasses, refunds, openDates)''',
)
text = text.replace(
    "func writeOutputs(classpasses []Classpass, refunds []Refund) error {",
    "func writeOutputs(classpasses []Classpass, refunds []Refund, openDates map[string]bool) error {",
)
text = text.replace(
    "matchIndex := findMatch(classpasses, refund, usedClasspasss)",
    "matchIndex := findMatch(classpasses, refund, usedClasspasss, openDates)",
)
start = text.index("func findMatch(")
end = text.index("\nfunc clean(", start)
text = text[:start] + '''func findMatch(classpasses []Classpass, refund Refund, used []bool, openDates map[string]bool) int {
\tbestIndex := -1
\tfor i := range classpasses {
\t\tif used[i] {
\t\t\tcontinue
\t\t}
\t\tclasspass := &classpasses[i]
\t\tif !openDates[refund.RefundDate] ||
\t\t\trefund.RefundDate == "" ||
\t\t\tclasspass.ClassDate == "" ||
\t\t\trefund.RefundDate > classpass.ClassDate ||
\t\t\tclasspass.ID != refund.ClasspassID ||
\t\t\tclasspass.Customer != refund.Customer ||
\t\t\tclasspass.Amount != refund.Amount ||
\t\t\tclasspass.Status != "BOOKED" ||
\t\t\t!allowedStudio(classpass.Studio) ||
\t\t\tclasspass.Studio != refund.Studio {
\t\t\tcontinue
\t\t}
\t\tif bestIndex < 0 || classpass.ClassDate > classpasses[bestIndex].ClassDate {
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
test -s /app/out/refund_report.csv
test -s /app/out/refund_summary.json
