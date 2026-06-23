#!/usr/bin/env bash
set -euo pipefail

cd /app

if grep -q 'func detectDatedMode' /app/cmd/reconcile/main.go; then
  /app/scripts/run_batch.sh
  test -s /app/out/adjustment_report.csv
  test -s /app/out/adjustment_summary.json
  exit 0
fi

if ! grep -q 'usedHauls' /app/cmd/reconcile/main.go; then
python3 <<'PY'
from pathlib import Path

path = Path("/app/cmd/reconcile/main.go")
text = path.read_text()
if '"strings"' not in text:
    text = text.replace('"strconv"', '"strconv"\n\t"strings"')
text = text.replace('amount, err := strconv.Atoi(row[2])', 'amount, err := strconv.Atoi(clean(row[2]))')
text = text.replace(
    'out = append(out, Haul{ID: row[0], Customer: row[1], Amount: amount, Status: row[3], Route: row[4]})',
    'out = append(out, Haul{ID: clean(row[0]), Customer: clean(row[1]), Amount: amount, Status: strings.ToUpper(clean(row[3])), Route: strings.ToUpper(clean(row[4]))})',
)
text = text.replace(
    'out = append(out, Adjustment{HaulID: row[0], Customer: row[1], Amount: amount, Route: row[3]})',
    'out = append(out, Adjustment{HaulID: clean(row[0]), Customer: clean(row[1]), Amount: amount, Route: clean(row[3])})',
)
text = text.replace(
    'summary.MatchedAmountCents -= adjustment.Amount',
    'summary.MatchedAmountCents += adjustment.Amount',
)
text = text.replace(
    'if len(haul.ID) >= 8 && len(adjustment.HaulID) >= 8 &&\n\t\t\thaul.ID[:8] == adjustment.HaulID[:8] &&',
    'if haul.ID == adjustment.HaulID &&',
)
text = text.replace(
    '\tsummary := Summary{}\n\tfor _, adjustment := range adjustments {\n\t\tmatch := findMatch(hauls, adjustment)',
    '\tsummary := Summary{}\n\tusedHauls := make([]bool, len(hauls))\n\tfor _, adjustment := range adjustments {\n\t\tmatchIndex := findMatch(hauls, adjustment, usedHauls)\n\t\tvar match *Haul\n\t\tif matchIndex >= 0 {\n\t\t\tmatch = &hauls[matchIndex]\n\t\t\tusedHauls[matchIndex] = true\n\t\t}',
)
text = text.replace(
    'func findMatch(hauls []Haul, adjustment Adjustment) *Haul {\n\tfor i := range hauls {\n\t\thaul := &hauls[i]\n\t\tif haul.ID == adjustment.HaulID &&',
    'func findMatch(hauls []Haul, adjustment Adjustment, used []bool) int {\n\tfor i := range hauls {\n\t\tif used[i] {\n\t\t\tcontinue\n\t\t}\n\t\thaul := &hauls[i]\n\t\tif haul.ID == adjustment.HaulID &&',
)
text = text.replace(
    '\t\t\treturn haul\n\t\t}\n\t}\n\treturn nil\n}',
    '\t\t\treturn i\n\t\t}\n\t}\n\treturn -1\n}',
)
text = text.replace(
    'func allowedRoute(route string) bool {\n\treturn route == "RESI" || route == "COMM" || route == "IND"\n}',
    'func clean(value string) string {\n\treturn strings.TrimSpace(value)\n}\n\nfunc allowedRoute(route string) bool {\n\troute = strings.ToUpper(clean(route))\n\treturn route == "RESI" || route == "COMM" || route == "IND"\n}',
)
path.write_text(text)
text = path.read_text()
text = text.replace('route = match.Route', 'route = clean(adjustment.Route)')
text = text.replace('haul.Route == adjustment.Route {', 'haul.Route == strings.ToUpper(clean(adjustment.Route)) {')
path.write_text(text)
PY
fi

if ! grep -q 'func canonicalRoute' /app/cmd/reconcile/main.go; then
python3 <<'PY'
from pathlib import Path

path = Path("/app/cmd/reconcile/main.go")
text = path.read_text()

text = text.replace(
    "Route: strings.ToUpper(clean(row[4]))",
    "Route: canonicalRoute(row[4])",
)
text = text.replace(
    "Route: strings.ToUpper(clean(row[3]))",
    "Route: canonicalRoute(row[3])",
)
text = text.replace(
    "Route: clean(row[3])",
    "Route: canonicalRoute(row[3])",
)
text = text.replace(
    "route = clean(adjustment.Route)",
    "route = match.Route",
)
text = text.replace(
    'func clean(value string) string {\n\treturn strings.TrimSpace(value)\n}\n\nfunc allowedRoute(route string) bool {\n\troute = strings.ToUpper(clean(route))\n\treturn route == "RESI" || route == "COMM" || route == "IND"\n}',
    '''func clean(value string) string {
\treturn strings.TrimSpace(value)
}

func canonicalRoute(route string) string {
\tswitch strings.ToUpper(clean(route)) {
\tcase "RES":
\t\treturn "RESI"
\tcase "COM":
\t\treturn "COMM"
\tcase "INDL":
\t\treturn "IND"
\tdefault:
\t\treturn strings.ToUpper(clean(route))
\t}
}

func allowedRoute(route string) bool {
\troute = canonicalRoute(route)
\treturn route == "RESI" || route == "COMM" || route == "IND"
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
    "type Haul struct {\n\tID       string\n\tCustomer string\n\tAmount   int\n\tStatus   string\n\tRoute   string\n}",
    "type Haul struct {\n\tID          string\n\tCustomer    string\n\tAmount      int\n\tStatus      string\n\tRoute       string\n\tServiceDate string\n}",
)
text = text.replace(
    "type Adjustment struct {\n\tHaulID string\n\tCustomer  string\n\tAmount    int\n\tRoute    string\n}",
    "type Adjustment struct {\n\tHaulID         string\n\tCustomer       string\n\tAmount         int\n\tRoute          string\n\tAdjustmentDate string\n}",
)
text = text.replace(
    "out = append(out, Haul{ID: clean(row[0]), Customer: clean(row[1]), Amount: amount, Status: strings.ToUpper(clean(row[3])), Route: canonicalRoute(row[4])})",
    '''serviceDate := ""
\t\tif len(row) > 5 {
\t\t\tserviceDate = clean(row[5])
\t\t}
\t\tout = append(out, Haul{ID: clean(row[0]), Customer: clean(row[1]), Amount: amount, Status: strings.ToUpper(clean(row[3])), Route: canonicalRoute(row[4]), ServiceDate: serviceDate})''',
)
text = text.replace(
    "out = append(out, Adjustment{HaulID: clean(row[0]), Customer: clean(row[1]), Amount: amount, Route: canonicalRoute(row[3])})",
    '''adjustmentDate := ""
\t\tif len(row) > 4 {
\t\t\tadjustmentDate = clean(row[4])
\t\t}
\t\tout = append(out, Adjustment{HaulID: clean(row[0]), Customer: clean(row[1]), Amount: amount, Route: canonicalRoute(row[3]), AdjustmentDate: adjustmentDate})''',
)
text = text.replace(
    "return writeOutputs(hauls, adjustments)",
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
\treturn writeOutputs(hauls, adjustments, openDates, datedMode)''',
)
text = text.replace(
    "func writeOutputs(hauls []Haul, adjustments []Adjustment) error {",
    "func writeOutputs(hauls []Haul, adjustments []Adjustment, openDates map[string]bool, datedMode bool) error {",
)
text = text.replace(
    "matchIndex := findMatch(hauls, adjustment, usedHauls)",
    "matchIndex := findMatch(hauls, adjustment, usedHauls, openDates, datedMode)",
)
start = text.index("func findMatch(")
end = text.index("\nfunc clean(", start)
text = text[:start] + '''func findMatch(hauls []Haul, adjustment Adjustment, used []bool, openDates map[string]bool, datedMode bool) int {
\tbestIndex := -1
\tfor i := range hauls {
\t\tif used[i] {
\t\t\tcontinue
\t\t}
\t\thaul := &hauls[i]
\t\tif datedMode {
\t\t\tif !openDates[adjustment.AdjustmentDate] ||
\t\t\t\tadjustment.AdjustmentDate == "" ||
\t\t\t\thaul.ServiceDate == "" ||
\t\t\t\tadjustment.AdjustmentDate > haul.ServiceDate {
\t\t\t\tcontinue
\t\t\t}
\t\t}
\t\tif haul.ID != adjustment.HaulID ||
\t\t\thaul.Customer != adjustment.Customer ||
\t\t\thaul.Amount != adjustment.Amount ||
\t\t\thaul.Status != "COMPLETED" ||
\t\t\t!allowedRoute(haul.Route) ||
\t\t\thaul.Route != adjustment.Route {
\t\t\tcontinue
\t\t}
\t\tif !datedMode {
\t\t\treturn i
\t\t}
\t\tif bestIndex < 0 ||
\t\t\thaul.ServiceDate > hauls[bestIndex].ServiceDate ||
\t\t\t(haul.ServiceDate == hauls[bestIndex].ServiceDate && i < bestIndex) {
\t\t\tbestIndex = i
\t\t}
\t}
\treturn bestIndex
}

func detectDatedMode() (bool, error) {
\thaulHeader, err := readHeader("/app/data/hauls.csv")
\tif err != nil {
\t\treturn false, err
\t}
\tadjustmentHeader, err := readHeader("/app/data/adjustments.csv")
\tif err != nil {
\t\treturn false, err
\t}
\treturn contains(haulHeader, "service_date") && contains(adjustmentHeader, "adjustment_date"), nil
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
test -s /app/out/adjustment_report.csv
test -s /app/out/adjustment_summary.json
