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
    'out = append(out, Lease{ID: row[0], Customer: row[1], Amount: amount, Status: row[3], UnitType: row[4]})',
    'out = append(out, Lease{ID: clean(row[0]), Customer: clean(row[1]), Amount: amount, Status: strings.ToUpper(clean(row[3])), UnitType: strings.ToUpper(clean(row[4]))})',
)
text = text.replace(
    'out = append(out, Credit{LeaseID: row[0], Customer: row[1], Amount: amount, UnitType: row[3]})',
    'out = append(out, Credit{LeaseID: clean(row[0]), Customer: clean(row[1]), Amount: amount, UnitType: strings.ToUpper(clean(row[3]))})',
)
text = text.replace(
    'summary.MatchedAmountCents -= credit.Amount',
    'summary.MatchedAmountCents += credit.Amount',
)
text = text.replace(
    'if len(lease.ID) >= 8 && len(credit.LeaseID) >= 8 &&\n\t\t\tlease.ID[:8] == credit.LeaseID[:8] &&',
    'if lease.ID == credit.LeaseID &&',
)
text = text.replace(
    'return unit_type == "SMALL" || unit_type == "MEDIUM" || unit_type == "LARGE"',
    'return unit_type == "SMALL" || unit_type == "MEDIUM" || unit_type == "LARGE"',
)
text = text.replace(
    '\tsummary := Summary{}\n\tfor _, credit := range credits {\n\t\tmatch := findMatch(leases, credit)',
    '\tsummary := Summary{}\n\tusedLeases := make([]bool, len(leases))\n\tfor _, credit := range credits {\n\t\tmatchIndex := findMatch(leases, credit, usedLeases)\n\t\tvar match *Lease\n\t\tif matchIndex >= 0 {\n\t\t\tmatch = &leases[matchIndex]\n\t\t\tusedLeases[matchIndex] = true\n\t\t}',
)
text = text.replace(
    'func findMatch(leases []Lease, credit Credit) *Lease {\n\tfor i := range leases {\n\t\tlease := &leases[i]\n\t\tif lease.ID == credit.LeaseID &&',
    'func findMatch(leases []Lease, credit Credit, used []bool) int {\n\tfor i := range leases {\n\t\tif used[i] {\n\t\t\tcontinue\n\t\t}\n\t\tlease := &leases[i]\n\t\tif lease.ID == credit.LeaseID &&',
)
text = text.replace(
    '\t\t\treturn lease\n\t\t}\n\t}\n\treturn nil\n}',
    '\t\t\treturn i\n\t\t}\n\t}\n\treturn -1\n}',
)
text = text.replace(
    'func allowedUnitType(unit_type string) bool {\n\treturn unit_type == "SMALL" || unit_type == "MEDIUM" || unit_type == "LARGE"\n}',
    'func clean(value string) string {\n\treturn strings.TrimSpace(value)\n}\n\nfunc allowedUnitType(unit_type string) bool {\n\tunit_type = strings.ToUpper(clean(unit_type))\n\treturn unit_type == "SMALL" || unit_type == "MEDIUM" || unit_type == "LARGE"\n}',
)
path.write_text(text)
PY

/app/scripts/run_batch.sh
test -s /app/out/credit_report.csv
test -s /app/out/credit_summary.json
