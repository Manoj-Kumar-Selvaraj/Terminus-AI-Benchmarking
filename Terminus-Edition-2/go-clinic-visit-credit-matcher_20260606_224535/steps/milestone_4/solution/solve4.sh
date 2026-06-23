#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

cd /app

if grep -q 'func loadEnabledChannels' /app/cmd/reconcile/main.go; then
  /app/scripts/run_batch.sh
  test -s /app/out/credit_report.csv
  test -s /app/out/credit_summary.json
  exit 0
fi

if ! grep -q 'func fileHasColumn' /app/cmd/reconcile/main.go; then
  bash "$SCRIPT_DIR/solve3.sh"
fi

python3 <<'PY'
from pathlib import Path

path = Path('/app/cmd/reconcile/main.go')
text = path.read_text()

text = text.replace(
    '''dated := fileHasColumn("/app/data/visits.csv", "due_date") ||
		fileHasColumn("/app/data/credits.csv", "credit_date")
	return writeOutputs(visits, credits, openDates, dated)''',
    '''dated := fileHasColumn("/app/data/visits.csv", "due_date") ||
		fileHasColumn("/app/data/credits.csv", "credit_date")
	enabledChannels, err := loadEnabledChannels("/app/config/methods.csv")
	if err != nil {
		return err
	}
	return writeOutputs(visits, credits, openDates, dated, enabledChannels)''',
)
text = text.replace(
    'func writeOutputs(visits []Visit, credits []Credit, openDates map[string]bool, dated bool) error {',
    'func writeOutputs(visits []Visit, credits []Credit, openDates map[string]bool, dated bool, enabledChannels map[string]bool) error {',
)
text = text.replace(
    'matchIndex := findMatch(visits, credit, usedVisits, openDates, dated)',
    'matchIndex := findMatch(visits, credit, usedVisits, openDates, dated, enabledChannels)',
)
text = text.replace(
    'func findMatch(visits []Visit, credit Credit, used []bool, openDates map[string]bool, dated bool) int {',
    'func findMatch(visits []Visit, credit Credit, used []bool, openDates map[string]bool, dated bool, enabledChannels map[string]bool) int {',
)
text = text.replace(
    '''		if visit.ID != credit.VisitID ||
			visit.Customer != credit.Customer ||
			visit.Amount != credit.Amount ||
			visit.Status != "POSTED" ||
			!allowedChannel(visit.Channel) ||
			visit.Channel != credit.Channel {''',
    '''		if visit.ID != credit.VisitID ||
			visit.Customer != credit.Customer ||
			visit.Amount != credit.Amount ||
			visit.Status != "POSTED" ||
			!allowedChannel(visit.Channel) ||
			!enabledChannels[visit.Channel] ||
			visit.Channel != credit.Channel {''',
)
insert_after = '''func loadOpenDates(path string) (map[string]bool, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	openDates := map[string]bool{}
	for _, line := range strings.Split(string(data), "\\n") {
		fields := strings.Fields(line)
		if len(fields) >= 2 && strings.EqualFold(fields[1], "open") {
			openDates[fields[0]] = true
		}
	}
	return openDates, nil
}
'''
addition = '''
func loadEnabledChannels(path string) (map[string]bool, error) {
	f, err := os.Open(path)
	if err != nil {
		return nil, err
	}
	defer f.Close()
	reader := csv.NewReader(f)
	reader.FieldsPerRecord = -1
	rows, err := reader.ReadAll()
	if err != nil {
		return nil, err
	}
	enabled := map[string]bool{}
	if len(rows) <= 1 {
		return enabled, nil
	}
	for _, row := range rows[1:] {
		if len(row) != 2 {
			continue
		}
		channel := strings.ToUpper(clean(row[0]))
		switch channel {
		case "ACH", "CARD", "WIRE":
			enabled[channel] = strings.EqualFold(clean(row[1]), "true")
		default:
			continue
		}
	}
	return enabled, nil
}
'''
if insert_after not in text:
    raise SystemExit('loadOpenDates block not found')
text = text.replace(insert_after, insert_after + addition)
path.write_text(text)
PY

/app/scripts/run_batch.sh
test -s /app/out/credit_report.csv
test -s /app/out/credit_summary.json
