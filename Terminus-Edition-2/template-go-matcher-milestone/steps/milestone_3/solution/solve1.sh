#!/usr/bin/env bash
set -euo pipefail

cd /app

python3 <<'PY'
from pathlib import Path

path = Path("/app/cmd/reconcile/main.go")
text = path.read_text()
if '"strings"' not in text:
    text = text.replace('"strconv"', '"strconv"\n\t"strings"')
text = text.replace('amount, err := strconv.Atoi(row[2])', 'amount, err := strconv.Atoi(clean(row[2]))')
text = text.replace(
    'out = append(out, Record{ID: row[0], Account: row[1], Amount: amount, Status: row[3], Tier: row[4]})',
    'out = append(out, Record{ID: clean(row[0]), Account: clean(row[1]), Amount: amount, Status: strings.ToUpper(clean(row[3])), Tier: strings.ToUpper(clean(row[4]))})',
)
text = text.replace(
    'out = append(out, Adjustment{RecordID: row[0], Account: row[1], Amount: amount, Tier: row[3]})',
    'out = append(out, Adjustment{RecordID: clean(row[0]), Account: clean(row[1]), Amount: amount, Tier: strings.ToUpper(clean(row[3]))})',
)
text = text.replace(
    'summary.MatchedAmountCents -= adjustment.Amount',
    'summary.MatchedAmountCents += adjustment.Amount',
)
text = text.replace(
    'if len(record.ID) >= 8 && len(adjustment.RecordID) >= 8 &&\n\t\t\trecord.ID[:8] == adjustment.RecordID[:8] &&',
    'if record.ID == adjustment.RecordID &&',
)
text = text.replace(
    '\tsummary := Summary{}\n\tfor _, adjustment := range adjustments {\n\t\tmatch := findMatch(records, adjustment)',
    '\tsummary := Summary{}\n\tusedRecords := make([]bool, len(records))\n\tfor _, adjustment := range adjustments {\n\t\tmatchIndex := findMatch(records, adjustment, usedRecords)\n\t\tvar match *Record\n\t\tif matchIndex >= 0 {\n\t\t\tmatch = &records[matchIndex]\n\t\t\tusedRecords[matchIndex] = true\n\t\t}',
)
text = text.replace(
    'func findMatch(records []Record, adjustment Adjustment) *Record {\n\tfor i := range records {\n\t\trecord := &records[i]\n\t\tif record.ID == adjustment.RecordID &&',
    'func findMatch(records []Record, adjustment Adjustment, used []bool) int {\n\tfor i := range records {\n\t\tif used[i] {\n\t\t\tcontinue\n\t\t}\n\t\trecord := &records[i]\n\t\tif record.ID == adjustment.RecordID &&',
)
text = text.replace(
    '\t\t\treturn record\n\t\t}\n\t}\n\treturn nil\n}',
    '\t\t\treturn i\n\t\t}\n\t}\n\treturn -1\n}',
)
text = text.replace(
    'func allowedTier(tier string) bool {\n\treturn tier == "TIER_A"\n}',
    'func clean(value string) string {\n\treturn strings.TrimSpace(value)\n}\n\nfunc allowedTier(tier string) bool {\n\ttier = strings.ToUpper(clean(tier))\n\treturn tier == "TIER_A" || tier == "TIER_B"\n}',
)
text = text.replace('wrong_report.csv', 'template_report.csv')
text = text.replace('wrong_summary.json', 'template_summary.json')
path.write_text(text)
PY

/app/scripts/run_batch.sh
test -s /app/out/template_report.csv
test -s /app/out/template_summary.json
