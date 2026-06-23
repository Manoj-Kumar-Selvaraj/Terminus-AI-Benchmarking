#!/usr/bin/env bash
set -euo pipefail

cd /app

if grep -q 'usedVisits' /app/cmd/reconcile/main.go; then
  /app/scripts/run_batch.sh
  test -s /app/out/credit_report.csv
  test -s /app/out/credit_summary.json
  exit 0
fi

python3 <<'PY'
from pathlib import Path

path = Path("/app/cmd/reconcile/main.go")
text = path.read_text()
text = text.replace('"strconv"', '"strconv"\n\t"strings"')
text = text.replace('amount, err := strconv.Atoi(row[2])', 'amount, err := strconv.Atoi(clean(row[2]))')
text = text.replace(
    'out = append(out, Visit{ID: row[0], Customer: row[1], Amount: amount, Status: row[3], Channel: row[4]})',
    'out = append(out, Visit{ID: clean(row[0]), Customer: clean(row[1]), Amount: amount, Status: strings.ToUpper(clean(row[3])), Channel: strings.ToUpper(clean(row[4]))})',
)
text = text.replace(
    'out = append(out, Credit{VisitID: row[0], Customer: row[1], Amount: amount, Channel: row[3]})',
    'out = append(out, Credit{VisitID: clean(row[0]), Customer: clean(row[1]), Amount: amount, Channel: strings.ToUpper(clean(row[3]))})',
)
text = text.replace(
    'summary.MatchedAmountCents -= credit.Amount',
    'summary.MatchedAmountCents += credit.Amount',
)
text = text.replace(
    'if len(visit.ID) >= 8 && len(credit.VisitID) >= 8 &&\n\t\t\tvisit.ID[:8] == credit.VisitID[:8] &&',
    'if visit.ID == credit.VisitID &&',
)
text = text.replace(
    'return channel == "ACH" || channel == "WIRE"',
    'return channel == "ACH" || channel == "CARD" || channel == "WIRE"',
)
text = text.replace(
    '\tsummary := Summary{}\n\tfor _, credit := range credits {\n\t\tmatch := findMatch(visits, credit)',
    '\tsummary := Summary{}\n\tusedVisits := make([]bool, len(visits))\n\tfor _, credit := range credits {\n\t\tmatchIndex := findMatch(visits, credit, usedVisits)\n\t\tvar match *Visit\n\t\tif matchIndex >= 0 {\n\t\t\tmatch = &visits[matchIndex]\n\t\t\tusedVisits[matchIndex] = true\n\t\t}',
)
text = text.replace(
    'func findMatch(visits []Visit, credit Credit) *Visit {\n\tfor i := range visits {\n\t\tvisit := &visits[i]\n\t\tif visit.ID == credit.VisitID &&',
    'func findMatch(visits []Visit, credit Credit, used []bool) int {\n\tfor i := range visits {\n\t\tif used[i] {\n\t\t\tcontinue\n\t\t}\n\t\tvisit := &visits[i]\n\t\tif visit.ID == credit.VisitID &&',
)
text = text.replace(
    '\t\t\treturn visit\n\t\t}\n\t}\n\treturn nil\n}',
    '\t\t\treturn i\n\t\t}\n\t}\n\treturn -1\n}',
)
text = text.replace(
    'func allowedChannel(channel string) bool {\n\treturn channel == "ACH" || channel == "CARD" || channel == "WIRE"\n}',
    'func clean(value string) string {\n\treturn strings.TrimSpace(value)\n}\n\nfunc allowedChannel(channel string) bool {\n\tchannel = strings.ToUpper(clean(channel))\n\treturn channel == "ACH" || channel == "CARD" || channel == "WIRE"\n}',
)
path.write_text(text)
PY

/app/scripts/run_batch.sh
test -s /app/out/credit_report.csv
test -s /app/out/credit_summary.json
