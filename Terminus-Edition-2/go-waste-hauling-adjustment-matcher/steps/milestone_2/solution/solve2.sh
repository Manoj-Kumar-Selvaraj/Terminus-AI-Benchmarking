#!/usr/bin/env bash
set -euo pipefail

cd /app

if grep -q 'func canonicalRoute' /app/cmd/reconcile/main.go; then
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

/app/scripts/run_batch.sh
test -s /app/out/adjustment_report.csv
test -s /app/out/adjustment_summary.json
