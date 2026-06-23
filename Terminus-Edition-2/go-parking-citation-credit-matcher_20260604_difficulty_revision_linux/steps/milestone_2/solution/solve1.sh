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
    'out = append(out, Citation{ID: row[0], Customer: row[1], Amount: amount, Status: row[3], Zone: row[4]})',
    'out = append(out, Citation{ID: clean(row[0]), Customer: clean(row[1]), Amount: amount, Status: strings.ToUpper(clean(row[3])), Zone: strings.ToUpper(clean(row[4]))})',
)
text = text.replace(
    'out = append(out, Credit{CitationID: row[0], Customer: row[1], Amount: amount, Zone: row[3]})',
    'out = append(out, Credit{CitationID: clean(row[0]), Customer: clean(row[1]), Amount: amount, Zone: strings.ToUpper(clean(row[3]))})',
)
text = text.replace(
    'summary.MatchedAmountCents -= credit.Amount',
    'summary.MatchedAmountCents += credit.Amount',
)
text = text.replace(
    'if len(citation.ID) >= 8 && len(credit.CitationID) >= 8 &&\n\t\t\tcitation.ID[:8] == credit.CitationID[:8] &&',
    'if citation.ID == credit.CitationID &&',
)
text = text.replace(
    'return zone == "STREET" || zone == "GARAGE" || zone == "LOT"',
    'return zone == "STREET" || zone == "GARAGE" || zone == "LOT"',
)
text = text.replace(
    '\tsummary := Summary{}\n\tfor _, credit := range credits {\n\t\tmatch := findMatch(citations, credit)',
    '\tsummary := Summary{}\n\tusedCitations := make([]bool, len(citations))\n\tfor _, credit := range credits {\n\t\tmatchIndex := findMatch(citations, credit, usedCitations)\n\t\tvar match *Citation\n\t\tif matchIndex >= 0 {\n\t\t\tmatch = &citations[matchIndex]\n\t\t\tusedCitations[matchIndex] = true\n\t\t}',
)
text = text.replace(
    'func findMatch(citations []Citation, credit Credit) *Citation {\n\tfor i := range citations {\n\t\tcitation := &citations[i]\n\t\tif citation.ID == credit.CitationID &&',
    'func findMatch(citations []Citation, credit Credit, used []bool) int {\n\tfor i := range citations {\n\t\tif used[i] {\n\t\t\tcontinue\n\t\t}\n\t\tcitation := &citations[i]\n\t\tif citation.ID == credit.CitationID &&',
)
text = text.replace(
    '\t\t\treturn citation\n\t\t}\n\t}\n\treturn nil\n}',
    '\t\t\treturn i\n\t\t}\n\t}\n\treturn -1\n}',
)
text = text.replace(
    'func allowedZone(zone string) bool {\n\treturn zone == "STREET" || zone == "GARAGE" || zone == "LOT"\n}',
    'func clean(value string) string {\n\treturn strings.TrimSpace(value)\n}\n\nfunc allowedZone(zone string) bool {\n\tzone = strings.ToUpper(clean(zone))\n\treturn zone == "STREET" || zone == "GARAGE" || zone == "LOT"\n}',
)
path.write_text(text)
PY

/app/scripts/run_batch.sh
test -s /app/out/credit_report.csv
test -s /app/out/credit_summary.json
