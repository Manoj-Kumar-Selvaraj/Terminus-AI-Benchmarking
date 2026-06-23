#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STEPS_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
bash "$SCRIPT_DIR/solve3.sh"

cd /app

python3 <<'PY'
from pathlib import Path

path = Path("/app/cmd/reconcile/main.go")
text = path.read_text()
if "loadAllowedReasons" in text:
    raise SystemExit(0)

text = text.replace(
    '\tcase "PRM":\n\t\treturn "PROMO"\n\tdefault:',
    '\tcase "PRM":\n\t\treturn "PROMO"\n\tcase "PUR":\n\t\treturn "PURCHASE"\n\tdefault:',
)
text = text.replace(
    "return writeOutputs(accruals, adjustments, openDates)",
    '''allowed, err := loadAllowedReasons("/app/config/reasons.csv")
\tif err != nil {
\t\treturn err
\t}
\treturn writeOutputs(accruals, adjustments, openDates, allowed)''',
)
text = text.replace(
    "func writeOutputs(accruals []Accrual, adjustments []Adjustment, openDates map[string]bool) error {",
    "func writeOutputs(accruals []Accrual, adjustments []Adjustment, openDates map[string]bool, allowedReasons map[string]bool) error {",
)
text = text.replace(
    "matchIndex := findMatch(accruals, adjustment, usedAccruals, openDates)",
    "matchIndex := findMatch(accruals, adjustment, usedAccruals, openDates, allowedReasons)",
)
text = text.replace(
    "func findMatch(accruals []Accrual, adjustment Adjustment, used []bool, openDates map[string]bool) int {",
    "func findMatch(accruals []Accrual, adjustment Adjustment, used []bool, openDates map[string]bool, allowedReasons map[string]bool) int {",
)
text = text.replace(
    "!allowedReason(accrual.Reason) ||",
    "!allowedReason(accrual.Reason, allowedReasons) ||",
)
text = text.replace(
    'func allowedReason(reason string) bool {\n\treason = canonicalReason(reason)\n\treturn reason == "PURCHASE" || reason == "BONUS" || reason == "PROMO"\n}',
    '''func loadAllowedReasons(path string) (map[string]bool, error) {
\trows, err := readRows(path)
\tif err != nil {
\t\treturn nil, err
\t}
\tout := map[string]bool{}
\tfor _, row := range rows {
\t\tif len(row) < 2 {
\t\t\tcontinue
\t\t}
\t\tif strings.EqualFold(clean(row[1]), "true") {
\t\t\tout[canonicalReason(row[0])] = true
\t\t}
\t}
\treturn out, nil
}

func allowedReason(reason string, allowed map[string]bool) bool {
\treason = canonicalReason(reason)
\treturn allowed[reason]
}''',
)

path.write_text(text)
PY

/app/scripts/run_batch.sh
test -s /app/out/adjustment_report.csv
test -s /app/out/adjustment_summary.json
