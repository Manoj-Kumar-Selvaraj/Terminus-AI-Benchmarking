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
    'out = append(out, Meter{ID: row[0], Customer: row[1], Amount: amount, Status: row[3], Channel: row[4]})',
    'out = append(out, Meter{ID: clean(row[0]), Customer: clean(row[1]), Amount: amount, Status: strings.ToUpper(clean(row[3])), Channel: strings.ToUpper(clean(row[4]))})',
)
text = text.replace(
    'out = append(out, Rebate{MeterID: row[0], Customer: row[1], Amount: amount, Channel: row[3]})',
    'out = append(out, Rebate{MeterID: clean(row[0]), Customer: clean(row[1]), Amount: amount, Channel: strings.ToUpper(clean(row[3]))})',
)
text = text.replace(
    'summary.MatchedAmountCents -= rebate.Amount',
    'summary.MatchedAmountCents += rebate.Amount',
)
text = text.replace(
    'if len(meter.ID) >= 8 && len(rebate.MeterID) >= 8 &&\n\t\t\tmeter.ID[:8] == rebate.MeterID[:8] &&',
    'if meter.ID == rebate.MeterID &&',
)
text = text.replace(
    'return channel == "ACH" || channel == "WIRE"',
    'return channel == "ACH" || channel == "CARD" || channel == "WIRE"',
)
text = text.replace(
    '\tsummary := Summary{}\n\tfor _, rebate := range rebates {\n\t\tmatch := findMatch(meters, rebate)',
    '\tsummary := Summary{}\n\tusedMeters := make([]bool, len(meters))\n\tfor _, rebate := range rebates {\n\t\tmatchIndex := findMatch(meters, rebate, usedMeters)\n\t\tvar match *Meter\n\t\tif matchIndex >= 0 {\n\t\t\tmatch = &meters[matchIndex]\n\t\t\tusedMeters[matchIndex] = true\n\t\t}',
)
text = text.replace(
    'func findMatch(meters []Meter, rebate Rebate) *Meter {\n\tfor i := range meters {\n\t\tmeter := &meters[i]\n\t\tif meter.ID == rebate.MeterID &&',
    'func findMatch(meters []Meter, rebate Rebate, used []bool) int {\n\tfor i := range meters {\n\t\tif used[i] {\n\t\t\tcontinue\n\t\t}\n\t\tmeter := &meters[i]\n\t\tif meter.ID == rebate.MeterID &&',
)
text = text.replace(
    '\t\t\treturn meter\n\t\t}\n\t}\n\treturn nil\n}',
    '\t\t\treturn i\n\t\t}\n\t}\n\treturn -1\n}',
)
text = text.replace(
    'func allowedChannel(channel string) bool {\n\treturn channel == "ACH" || channel == "CARD" || channel == "WIRE"\n}',
    'func clean(value string) string {\n\treturn strings.TrimSpace(value)\n}\n\nfunc allowedChannel(channel string) bool {\n\tchannel = strings.ToUpper(clean(channel))\n\treturn channel == "ACH" || channel == "CARD" || channel == "WIRE"\n}',
)
path.write_text(text)
PY

/app/scripts/run_batch.sh
test -s /app/out/rebate_report.csv
test -s /app/out/rebate_summary.json
