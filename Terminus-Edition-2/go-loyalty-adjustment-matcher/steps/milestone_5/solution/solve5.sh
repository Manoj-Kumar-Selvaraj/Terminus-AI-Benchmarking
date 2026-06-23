#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STEPS_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
bash "$SCRIPT_DIR/solve4.sh"

cd /app

python3 <<'PY'
from pathlib import Path

path = Path("/app/cmd/reconcile/main.go")
text = path.read_text()
if "loadEarnLookback" in text:
    raise SystemExit(0)

if '"time"' not in text:
    text = text.replace('"strconv"', '"strconv"\n\t"time"')

text = text.replace(
    "return writeOutputs(accruals, adjustments, openDates, allowed)",
    '''lookback, err := loadEarnLookback("/app/config/job.properties")
\tif err != nil {
\t\treturn err
\t}
\treturn writeOutputs(accruals, adjustments, openDates, allowed, lookback)''',
)
text = text.replace(
    "func writeOutputs(accruals []Accrual, adjustments []Adjustment, openDates map[string]bool, allowedReasons map[string]bool) error {",
    "func writeOutputs(accruals []Accrual, adjustments []Adjustment, openDates map[string]bool, allowedReasons map[string]bool, earnLookback int) error {",
)
text = text.replace(
    "matchIndex := findMatch(accruals, adjustment, usedAccruals, openDates, allowedReasons)",
    "matchIndex := findMatch(accruals, adjustment, usedAccruals, openDates, allowedReasons, earnLookback)",
)
text = text.replace(
    "func findMatch(accruals []Accrual, adjustment Adjustment, used []bool, openDates map[string]bool, allowedReasons map[string]bool) int {",
    "func findMatch(accruals []Accrual, adjustment Adjustment, used []bool, openDates map[string]bool, allowedReasons map[string]bool, earnLookback int) int {",
)
text = text.replace(
    "\t\t\taccrual.Reason != adjustment.Reason {\n\t\t\tcontinue\n\t\t}",
    "\t\t\taccrual.Reason != adjustment.Reason ||\n\t\t\topenDaysAfterEarn(accrual.EarnDate, adjustment.AdjustmentDate, openDates) > earnLookback {\n\t\t\tcontinue\n\t\t}",
)
text = text.replace(
    "func loadAllowedReasons(path string) (map[string]bool, error) {",
    '''func loadEarnLookback(path string) (int, error) {
\tdata, err := os.ReadFile(path)
\tif err != nil {
\t\treturn 0, err
\t}
\tfor _, line := range strings.Split(string(data), "\\n") {
\t\tline = strings.TrimSpace(line)
\t\tif strings.HasPrefix(line, "earn_lookback_open_days=") {
\t\t\treturn strconv.Atoi(strings.TrimPrefix(line, "earn_lookback_open_days="))
\t\t}
\t}
\treturn 0, nil
}

func openDaysAfterEarn(earnDate, adjustmentDate string, openDates map[string]bool) int {
\tstart, err1 := time.Parse("2006-01-02", earnDate)
\tend, err2 := time.Parse("2006-01-02", adjustmentDate)
\tif err1 != nil || err2 != nil {
\t\treturn 1 << 30
\t}
\tcount := 0
\tfor d := start.AddDate(0, 0, 1); !d.After(end); d = d.AddDate(0, 0, 1) {
\t\tif openDates[d.Format("2006-01-02")] {
\t\t\tcount++
\t\t}
\t}
\treturn count
}

func loadAllowedReasons(path string) (map[string]bool, error) {''',
)

path.write_text(text)
PY

/app/scripts/run_batch.sh
test -s /app/out/adjustment_report.csv
test -s /app/out/adjustment_summary.json
