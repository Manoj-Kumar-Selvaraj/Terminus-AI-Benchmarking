#!/usr/bin/env bash
set -euo pipefail

cd /app

if grep -q 'func loadMethods' /app/cmd/reconcile/main.go; then
  /app/scripts/run_batch.sh
  test -s /app/out/tab_adjustment_report.csv
  test -s /app/out/tab_adjustment_summary.json
  exit 0
fi

if ! grep -q 'func loadOpenDates' /app/cmd/reconcile/main.go; then
  SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  bash "$SCRIPT_DIR/solve3.sh"
fi

python3 <<'PY'
from pathlib import Path

path = Path('/app/cmd/reconcile/main.go')
text = path.read_text()

text = text.replace('loadTripes', 'loadTrips')
text = text.replace('pass_type = match.PassType', 'pass_type = credit.PassType')

old_credit_struct = '''type Credit struct {
	TripID     string
	Customer   string
	Amount     int
	PassType   string
	CreditDate string
}'''
new_credit_struct = '''type Credit struct {
	TripID        string
	Customer      string
	Amount        int
	PassType      string
	CreditDate    string
	Method        string
	MethodPresent bool
}'''
if old_credit_struct not in text:
    raise SystemExit('expected milestone 3 Credit struct not found')
text = text.replace(old_credit_struct, new_credit_struct)

old_run = '''openDates, err := loadOpenDates("/app/config/cutoff_calendar.txt")
	if err != nil {
		return err
	}
	return writeOutputs(trips, credits, openDates)'''
new_run = '''openDates, err := loadOpenDates("/app/config/cutoff_calendar.txt")
	if err != nil {
		return err
	}
	enabledMethods, err := loadMethods("/app/config/methods.csv")
	if err != nil {
		return err
	}
	return writeOutputs(trips, credits, openDates, enabledMethods)'''
if old_run not in text:
    raise SystemExit('expected milestone 3 run block not found')
text = text.replace(old_run, new_run)

old_credit_append = '''adjustDate := ""
		if len(row) > 4 {
			adjustDate = clean(row[4])
		}
		out = append(out, Credit{TripID: clean(row[0]), Customer: clean(row[1]), Amount: amount, PassType: canonicalPassType(row[3]), CreditDate: adjustDate})'''
new_credit_append = '''adjustDate := ""
		if len(row) > 4 {
			adjustDate = clean(row[4])
		}
		adjustMethod := ""
		methodPresent := false
		if len(row) > 5 {
			adjustMethod = strings.ToUpper(clean(row[5]))
			methodPresent = true
		}
		out = append(out, Credit{TripID: clean(row[0]), Customer: clean(row[1]), Amount: amount, PassType: canonicalPassType(row[3]), CreditDate: adjustDate, Method: adjustMethod, MethodPresent: methodPresent})'''
if old_credit_append not in text:
    raise SystemExit('expected milestone 3 loadCredits append block not found')
text = text.replace(old_credit_append, new_credit_append)

text = text.replace(
    'func writeOutputs(trips []Trip, credits []Credit, openDates map[string]bool) error {',
    'func writeOutputs(trips []Trip, credits []Credit, openDates map[string]bool, enabledMethods map[string]bool) error {',
)
text = text.replace(
    'matchIndex := findMatch(trips, credit, usedRecords, openDates)',
    'matchIndex := findMatch(trips, credit, usedRecords, openDates, enabledMethods)',
)

old_find_start = '''func findMatch(trips []Trip, credit Credit, used []bool, openDates map[string]bool) int {
	bestIndex := -1
	for i := range trips {
		trip := &trips[i]
		if used[i] {
			continue
		}'''
new_find_start = '''func findMatch(trips []Trip, credit Credit, used []bool, openDates map[string]bool, enabledMethods map[string]bool) int {
	bestIndex := -1
	for i := range trips {
		trip := &trips[i]
		if used[i] {
			continue
		}
		if credit.MethodPresent && !enabledMethods[credit.Method] {
			continue
		}'''
if old_find_start not in text:
    raise SystemExit('expected milestone 3 findMatch start not found')
text = text.replace(old_find_start, new_find_start)

load_methods = '''
func loadMethods(path string) (map[string]bool, error) {
	rows, err := readRows(path)
	if err != nil {
		return nil, err
	}
	enabled := map[string]bool{}
	for _, row := range rows {
		if len(row) < 2 {
			continue
		}
		method := strings.ToUpper(clean(row[0]))
		if method == "" {
			continue
		}
		if strings.ToLower(clean(row[1])) == "true" {
			enabled[method] = true
		}
	}
	return enabled, nil
}

'''
marker = '\nfunc validDate(value string) bool {'
if marker not in text:
    raise SystemExit('validDate marker not found')
text = text.replace(marker, '\n' + load_methods + 'func validDate(value string) bool {')

path.write_text(text)
PY

gofmt -w /app/cmd/reconcile/main.go
/app/scripts/run_batch.sh
test -s /app/out/tab_adjustment_report.csv
test -s /app/out/tab_adjustment_summary.json
