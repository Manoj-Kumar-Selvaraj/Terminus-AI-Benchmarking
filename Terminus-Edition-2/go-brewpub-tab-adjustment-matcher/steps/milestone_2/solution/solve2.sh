#!/usr/bin/env bash
set -euo pipefail

cd /app

if grep -q 'func canonicalPassType' /app/cmd/reconcile/main.go; then
  /app/scripts/run_batch.sh
  test -s /app/out/tab_adjustment_report.csv
  test -s /app/out/tab_adjustment_summary.json
  exit 0
fi

if ! grep -q 'func clean(value string)' /app/cmd/reconcile/main.go; then
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

/app/scripts/run_batch.sh
test -s /app/out/tab_adjustment_report.csv
test -s /app/out/tab_adjustment_summary.json
