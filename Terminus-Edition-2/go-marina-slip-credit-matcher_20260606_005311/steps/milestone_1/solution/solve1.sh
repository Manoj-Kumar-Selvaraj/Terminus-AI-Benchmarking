#!/usr/bin/env bash
set -euo pipefail

cd /app

python3 <<'PY'
from pathlib import Path

path = Path("/app/cmd/reconcile/main.go")
text = path.read_text()
text = text.replace('"strconv"', '"strconv"\n\t"strings"')
text = text.replace('amount, err := strconv.Atoi(row[2])', 'amount, err := strconv.Atoi(clean(row[2]))')
text = text.replace(
    'out = append(out, Slip{ID: row[0], Customer: row[1], Amount: amount, Status: row[3], DockZone: row[4]})',
    'out = append(out, Slip{ID: clean(row[0]), Customer: clean(row[1]), Amount: amount, Status: strings.ToUpper(clean(row[3])), DockZone: strings.ToUpper(clean(row[4]))})',
)
text = text.replace(
    'out = append(out, Credit{SlipID: row[0], Customer: row[1], Amount: amount, DockZone: row[3]})',
    'out = append(out, Credit{SlipID: clean(row[0]), Customer: clean(row[1]), Amount: amount, DockZone: clean(row[3])})',
)
text = text.replace(
    'summary.MatchedAmountCents -= credit.Amount',
    'summary.MatchedAmountCents += credit.Amount',
)
text = text.replace(
    'dock_zone = match.DockZone',
    'dock_zone = credit.DockZone',
)
text = text.replace(
    'if len(slip.ID) >= 8 && len(credit.SlipID) >= 8 &&\n\t\t\tslip.ID[:8] == credit.SlipID[:8] &&',
    'if slip.ID == credit.SlipID &&',
)
text = text.replace(
    'return dock_zone == "NORTH" || dock_zone == "SOUTH" || dock_zone == "EAST"',
    'return dock_zone == "NORTH" || dock_zone == "SOUTH" || dock_zone == "EAST"',
)
text = text.replace(
    '\tsummary := Summary{}\n\tfor _, credit := range credits {\n\t\tmatch := findMatch(slips, credit)',
    '\tsummary := Summary{}\n\tusedSlips := make([]bool, len(slips))\n\tfor _, credit := range credits {\n\t\tmatchIndex := findMatch(slips, credit, usedSlips)\n\t\tvar match *Slip\n\t\tif matchIndex >= 0 {\n\t\t\tmatch = &slips[matchIndex]\n\t\t\tusedSlips[matchIndex] = true\n\t\t}',
)
text = text.replace(
    'func findMatch(slips []Slip, credit Credit) *Slip {\n\tfor i := range slips {\n\t\tslip := &slips[i]\n\t\tif slip.ID == credit.SlipID &&',
    'func findMatch(slips []Slip, credit Credit, used []bool) int {\n\tfor i := range slips {\n\t\tif used[i] {\n\t\t\tcontinue\n\t\t}\n\t\tslip := &slips[i]\n\t\tif slip.ID == credit.SlipID &&',
)
text = text.replace(
    'slip.DockZone == credit.DockZone {',
    'slip.DockZone == strings.ToUpper(clean(credit.DockZone)) {',
)
text = text.replace(
    '\t\t\treturn slip\n\t\t}\n\t}\n\treturn nil\n}',
    '\t\t\treturn i\n\t\t}\n\t}\n\treturn -1\n}',
)
text = text.replace(
    'func allowedDockZone(dock_zone string) bool {\n\treturn dock_zone == "NORTH" || dock_zone == "SOUTH" || dock_zone == "EAST"\n}',
    'func clean(value string) string {\n\treturn strings.TrimSpace(value)\n}\n\nfunc allowedDockZone(dock_zone string) bool {\n\tdock_zone = strings.ToUpper(clean(dock_zone))\n\treturn dock_zone == "NORTH" || dock_zone == "SOUTH" || dock_zone == "EAST"\n}',
)
path.write_text(text)
PY

/app/scripts/run_batch.sh
test -s /app/out/credit_report.csv
test -s /app/out/credit_summary.json
