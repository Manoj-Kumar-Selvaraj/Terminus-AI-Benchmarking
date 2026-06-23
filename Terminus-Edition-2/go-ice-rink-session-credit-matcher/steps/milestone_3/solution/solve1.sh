#!/usr/bin/env bash
set -euo pipefail

cd /app

python3 <<'PY'
from pathlib import Path

path = Path("/app/cmd/reconcile/main.go")
text = path.read_text()
if "func clean(value string)" in text:
    raise SystemExit(0)
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
    'func allowedPassType(pass_type string) bool {\n\treturn pass_type == "PRAC" || pass_type == "GAME" || pass_type == "LEAG"\n}',
    'func clean(value string) string {\n\treturn strings.TrimSpace(value)\n}\n\nfunc allowedPassType(pass_type string) bool {\n\tpass_type = strings.ToUpper(clean(pass_type))\n\treturn pass_type == "PRAC" || pass_type == "GAME" || pass_type == "LEAG"\n}',
)
text = text.replace(
    'return os.WriteFile("/app/out/credit_summary.json"',
    'return os.WriteFile("/app/out/rink_credit_summary.json"',
)
path.write_text(text)
PY

/app/scripts/run_batch.sh
test -s /app/out/rink_credit_report.csv
test -s /app/out/rink_credit_summary.json
