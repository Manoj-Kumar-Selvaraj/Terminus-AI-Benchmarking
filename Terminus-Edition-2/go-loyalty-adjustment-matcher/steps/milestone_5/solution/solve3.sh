#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STEPS_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
bash "$SCRIPT_DIR/solve2.sh"

cd /app

python3 <<'PY'
from pathlib import Path

path = Path("/app/cmd/reconcile/main.go")
text = path.read_text()
if "EarnDate" in text and "loadOpenDates" in text:
    raise SystemExit(0)

text = text.replace(
    "type Accrual struct {\n\tID       string\n\tMember string\n\tAmount   int\n\tStatus   string\n\tReason   string\n}",
    "type Accrual struct {\n\tID          string\n\tMember      string\n\tAmount      int\n\tStatus      string\n\tReason      string\n\tEarnDate string\n}",
)
text = text.replace(
    "type Adjustment struct {\n\tAccrualID string\n\tMember  string\n\tAmount    int\n\tReason    string\n}",
    "type Adjustment struct {\n\tAccrualID       string\n\tMember       string\n\tAmount       int\n\tReason       string\n\tAdjustmentDate string\n}",
)
text = text.replace(
    "out = append(out, Accrual{ID: clean(row[0]), Member: clean(row[1]), Amount: amount, Status: strings.ToUpper(clean(row[3])), Reason: canonicalReason(row[4])})",
    '''serviceDate := ""
\t\tif len(row) > 5 {
\t\t\tserviceDate = clean(row[5])
\t\t}
\t\tout = append(out, Accrual{ID: clean(row[0]), Member: clean(row[1]), Amount: amount, Status: strings.ToUpper(clean(row[3])), Reason: canonicalReason(row[4]), EarnDate: serviceDate})''',
)
text = text.replace(
    "out = append(out, Adjustment{AccrualID: clean(row[0]), Member: clean(row[1]), Amount: amount, Reason: canonicalReason(row[3])})",
    '''adjustmentDate := ""
\t\tif len(row) > 4 {
\t\t\tadjustmentDate = clean(row[4])
\t\t}
\t\tout = append(out, Adjustment{AccrualID: clean(row[0]), Member: clean(row[1]), Amount: amount, Reason: canonicalReason(row[3]), AdjustmentDate: adjustmentDate})''',
)
text = text.replace(
    "return writeOutputs(accruals, adjustments)",
    '''openDates, err := loadOpenDates("/app/config/cutoff_calendar.txt")
\tif err != nil {
\t\treturn err
\t}
\treturn writeOutputs(accruals, adjustments, openDates)''',
)
text = text.replace(
    "func writeOutputs(accruals []Accrual, adjustments []Adjustment) error {",
    "func writeOutputs(accruals []Accrual, adjustments []Adjustment, openDates map[string]bool) error {",
)
text = text.replace(
    "matchIndex := findMatch(accruals, adjustment, usedAccruals)",
    "matchIndex := findMatch(accruals, adjustment, usedAccruals, openDates)",
)
start = text.index("func findMatch(")
end = text.index("\nfunc clean(", start)
text = text[:start] + '''func findMatch(accruals []Accrual, adjustment Adjustment, used []bool, openDates map[string]bool) int {
\tbestIndex := -1
\tfor i := range accruals {
\t\tif used[i] {
\t\t\tcontinue
\t\t}
\t\taccrual := &accruals[i]
\t\tif !openDates[adjustment.AdjustmentDate] ||
\t\t\tadjustment.AdjustmentDate == "" ||
\t\t\taccrual.EarnDate == "" ||
\t\t\taccrual.EarnDate > adjustment.AdjustmentDate ||
\t\t\taccrual.ID != adjustment.AccrualID ||
\t\t\taccrual.Member != adjustment.Member ||
\t\t\taccrual.Amount != adjustment.Amount ||
\t\t\taccrual.Status != "POSTED" ||
\t\t\t!allowedReason(accrual.Reason) ||
\t\t\taccrual.Reason != adjustment.Reason {
\t\t\tcontinue
\t\t}
\t\tif bestIndex < 0 ||
\t\t\taccrual.EarnDate > accruals[bestIndex].EarnDate ||
\t\t\t(accrual.EarnDate == accruals[bestIndex].EarnDate && i < bestIndex) {
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
test -s /app/out/adjustment_report.csv
test -s /app/out/adjustment_summary.json
