#!/usr/bin/env bash
set -euo pipefail

cd /app

if grep -q 'func dateMode' /app/cmd/reconcile/main.go; then
  /app/scripts/run_batch.sh
  test -s /app/out/refund_report.csv
  test -s /app/out/refund_summary.json
  exit 0
fi

if ! grep -q 'func canonicalStallType' /app/cmd/reconcile/main.go; then
  if ! grep -q 'usedRecords' /app/cmd/reconcile/main.go; then
python3 <<'PY'
from pathlib import Path

path = Path("/app/cmd/reconcile/main.go")
text = path.read_text()
if '"strings"' not in text:
    text = text.replace('"strconv"', '"strconv"\n\t"strings"')
text = text.replace('amount, err := strconv.Atoi(row[2])', 'amount, err := strconv.Atoi(clean(row[2]))')
text = text.replace(
    'out = append(out, Stall{ID: row[0], Customer: row[1], Amount: amount, Status: row[3], StallType: row[4]})',
    'out = append(out, Stall{ID: clean(row[0]), Customer: clean(row[1]), Amount: amount, Status: strings.ToUpper(clean(row[3])), StallType: strings.ToUpper(clean(row[4]))})',
)
text = text.replace(
    'out = append(out, Refund{StallID: row[0], Customer: row[1], Amount: amount, StallType: row[3]})',
    'out = append(out, Refund{StallID: clean(row[0]), Customer: clean(row[1]), Amount: amount, StallType: strings.ToUpper(clean(row[3]))})',
)
text = text.replace(
    'summary.MatchedAmountCents -= refund.Amount',
    'summary.MatchedAmountCents += refund.Amount',
)
text = text.replace(
    'if len(stall.ID) >= 8 && len(refund.StallID) >= 8 &&\n\t\t\tstall.ID[:8] == refund.StallID[:8] &&',
    'if stall.ID == refund.StallID &&',
)
text = text.replace(
    '\tsummary := Summary{}\n\tfor _, refund := range refunds {\n\t\tmatch := findMatch(stalls, refund)',
    '\tsummary := Summary{}\n\tusedRecords := make([]bool, len(stalls))\n\tfor _, refund := range refunds {\n\t\tmatchIndex := findMatch(stalls, refund, usedRecords)\n\t\tvar match *Stall\n\t\tif matchIndex >= 0 {\n\t\t\tmatch = &stalls[matchIndex]\n\t\t\tusedRecords[matchIndex] = true\n\t\t}',
)
text = text.replace(
    'func findMatch(stalls []Stall, refund Refund) *Stall {\n\tfor i := range stalls {\n\t\tstall := &stalls[i]\n\t\tif stall.ID == refund.StallID &&',
    'func findMatch(stalls []Stall, refund Refund, used []bool) int {\n\tfor i := range stalls {\n\t\tif used[i] {\n\t\t\tcontinue\n\t\t}\n\t\tstall := &stalls[i]\n\t\tif stall.ID == refund.StallID &&',
)
text = text.replace(
    '\t\t\treturn stall\n\t\t}\n\t}\n\treturn nil\n}',
    '\t\t\treturn i\n\t\t}\n\t}\n\treturn -1\n}',
)
text = text.replace(
    'func allowedStallType(stallType string) bool {\n\tstallType = strings.ToUpper(strings.TrimSpace(stallType))\n\treturn stallType == "PRODUCE" || stallType == "CRAFT"\n}',
    'func clean(value string) string {\n\treturn strings.TrimSpace(value)\n}\n\nfunc allowedStallType(stallType string) bool {\n\tstallType = strings.ToUpper(clean(stallType))\n\treturn stallType == "PRODUCE" || stallType == "CRAFT" || stallType == "FOOD"\n}',
)
text = text.replace(
    'stallType = match.StallType',
    'stallType = refund.StallType',
)
path.write_text(text)
PY
  fi

python3 <<'PY'
from pathlib import Path

path = Path("/app/cmd/reconcile/main.go")
text = path.read_text()

text = text.replace(
    "StallType: strings.ToUpper(clean(row[4]))",
    "StallType: canonicalStallType(row[4])",
)
text = text.replace(
    "StallType: strings.ToUpper(clean(row[3]))",
    "StallType: canonicalStallType(row[3])",
)
text = text.replace(
    'func clean(value string) string {\n\treturn strings.TrimSpace(value)\n}\n\nfunc allowedStallType(stallType string) bool {\n\tstallType = strings.ToUpper(clean(stallType))\n\treturn stallType == "PRODUCE" || stallType == "CRAFT" || stallType == "FOOD"\n}',
    '''func clean(value string) string {
\treturn strings.TrimSpace(value)
}

func canonicalStallType(stallType string) string {
\tswitch strings.ToUpper(clean(stallType)) {
\tcase "PRD":
\t\treturn "PRODUCE"
\tcase "CRT":
\t\treturn "CRAFT"
\tcase "FOD":
\t\treturn "FOOD"
\tdefault:
\t\treturn strings.ToUpper(clean(stallType))
\t}
}

func allowedStallType(stallType string) bool {
\tstallType = canonicalStallType(stallType)
\treturn stallType == "PRODUCE" || stallType == "CRAFT" || stallType == "FOOD"
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
    "type Stall struct {\n\tID        string\n\tCustomer  string\n\tAmount    int\n\tStatus    string\n\tStallType string\n}",
    "type Stall struct {\n\tID         string\n\tCustomer   string\n\tAmount     int\n\tStatus     string\n\tStallType  string\n\tMarketDate string\n}",
)
text = text.replace(
    "type Refund struct {\n\tStallID   string\n\tCustomer  string\n\tAmount    int\n\tStallType string\n}",
    "type Refund struct {\n\tStallID     string\n\tCustomer   string\n\tAmount     int\n\tStallType  string\n\tRefundDate string\n}",
)
text = text.replace(
    "out = append(out, Stall{ID: clean(row[0]), Customer: clean(row[1]), Amount: amount, Status: strings.ToUpper(clean(row[3])), StallType: canonicalStallType(row[4])})",
    '''dueDate := ""
\t\tif len(row) > 5 {
\t\t\tdueDate = clean(row[5])
\t\t}
\t\tout = append(out, Stall{ID: clean(row[0]), Customer: clean(row[1]), Amount: amount, Status: strings.ToUpper(clean(row[3])), StallType: canonicalStallType(row[4]), MarketDate: dueDate})''',
)
text = text.replace(
    "out = append(out, Refund{StallID: clean(row[0]), Customer: clean(row[1]), Amount: amount, StallType: canonicalStallType(row[3])})",
    '''refundDate := ""
\t\tif len(row) > 4 {
\t\t\trefundDate = clean(row[4])
\t\t}
\t\tout = append(out, Refund{StallID: clean(row[0]), Customer: clean(row[1]), Amount: amount, StallType: canonicalStallType(row[3]), RefundDate: refundDate})''',
)
text = text.replace(
    "return writeOutputs(stalls, refunds)",
    '''openDates, err := loadOpenDates("/app/config/cutoff_calendar.txt")
\tif err != nil {
\t\treturn err
\t}
\treturn writeOutputs(stalls, refunds, openDates)''',
)
text = text.replace(
    "func writeOutputs(stalls []Stall, refunds []Refund) error {",
    "func writeOutputs(stalls []Stall, refunds []Refund, openDates map[string]bool) error {",
)
text = text.replace(
    "func writeOutputs(stalls []Stall, refunds []Refund, openDates map[string]bool) error {",
    "func dateMode(stalls []Stall, refunds []Refund) bool {\n\tfor _, stall := range stalls {\n\t\tif stall.MarketDate != \"\" {\n\t\t\treturn true\n\t\t}\n\t}\n\tfor _, refund := range refunds {\n\t\tif refund.RefundDate != \"\" {\n\t\t\treturn true\n\t\t}\n\t}\n\treturn false\n}\n\nfunc writeOutputs(stalls []Stall, refunds []Refund, openDates map[string]bool) error {",
)
text = text.replace(
    "matchIndex := findMatch(stalls, refund, usedRecords)",
    "matchIndex := findMatch(stalls, refund, usedRecords, openDates, dateMode(stalls, refunds))",
)
start = text.index("func findMatch(")
end = text.index("\nfunc clean(", start)
text = text[:start] + '''func findMatch(stalls []Stall, refund Refund, used []bool, openDates map[string]bool, dated bool) int {
\tbestIndex := -1
\tfor i := range stalls {
\t\tif used[i] {
\t\t\tcontinue
\t\t}
\t\tstall := &stalls[i]
\t\tif stall.ID != refund.StallID ||
\t\t\tstall.Customer != refund.Customer ||
\t\t\tstall.Amount != refund.Amount ||
\t\t\tstall.Status != "RESERVED" ||
\t\t\t!allowedStallType(stall.StallType) ||
\t\t\tstall.StallType != refund.StallType {
\t\t\tcontinue
\t\t}
\t\tif dated {
\t\t\tif stall.MarketDate == "" && refund.RefundDate == "" {
\t\t\t\t// undated backward compatibility when date columns exist but values are blank
\t\t\t} else {
\t\t\t\tif stall.MarketDate == "" || refund.RefundDate == "" {
\t\t\t\t\tcontinue
\t\t\t\t}
\t\t\t\tif !openDates[refund.RefundDate] {
\t\t\t\t\tcontinue
\t\t\t\t}
\t\t\t\tif refund.RefundDate > stall.MarketDate {
\t\t\t\t\tcontinue
\t\t\t\t}
\t\t\t}
\t\t}
\t\tif bestIndex < 0 {
\t\t\tbestIndex = i
\t\t} else if dated && stall.MarketDate > stalls[bestIndex].MarketDate {
\t\t\tbestIndex = i
\t\t} else if dated && stall.MarketDate == stalls[bestIndex].MarketDate && i < bestIndex {
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
