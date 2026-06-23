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
    'out = append(out, Vehicle{ID: row[0], Customer: row[1], Amount: amount, Status: row[3], Channel: row[4]})',
    'out = append(out, Vehicle{ID: clean(row[0]), Customer: clean(row[1]), Amount: amount, Status: strings.ToUpper(clean(row[3])), Channel: strings.ToUpper(clean(row[4]))})',
)
text = text.replace(
    'out = append(out, Rebate{VehicleID: row[0], Customer: row[1], Amount: amount, Channel: row[3]})',
    'out = append(out, Rebate{VehicleID: clean(row[0]), Customer: clean(row[1]), Amount: amount, Channel: strings.ToUpper(clean(row[3]))})',
)
text = text.replace(
    'summary.MatchedAmountCents -= rebate.Amount',
    'summary.MatchedAmountCents += rebate.Amount',
)
text = text.replace(
    'if len(vehicle.ID) >= 8 && len(rebate.VehicleID) >= 8 &&\n\t\t\tvehicle.ID[:8] == rebate.VehicleID[:8] &&',
    'if vehicle.ID == rebate.VehicleID &&',
)
text = text.replace(
    'return channel == "ACH" || channel == "WIRE"',
    'return channel == "ACH" || channel == "CARD" || channel == "WIRE"',
)
text = text.replace(
    '\tsummary := Summary{}\n\tfor _, rebate := range rebates {\n\t\tmatch := findMatch(vehicles, rebate)',
    '\tsummary := Summary{}\n\tusedVehicles := make([]bool, len(vehicles))\n\tfor _, rebate := range rebates {\n\t\tmatchIndex := findMatch(vehicles, rebate, usedVehicles)\n\t\tvar match *Vehicle\n\t\tif matchIndex >= 0 {\n\t\t\tmatch = &vehicles[matchIndex]\n\t\t\tusedVehicles[matchIndex] = true\n\t\t}',
)
text = text.replace(
    'func findMatch(vehicles []Vehicle, rebate Rebate) *Vehicle {\n\tfor i := range vehicles {\n\t\tvehicle := &vehicles[i]\n\t\tif vehicle.ID == rebate.VehicleID &&',
    'func findMatch(vehicles []Vehicle, rebate Rebate, used []bool) int {\n\tfor i := range vehicles {\n\t\tif used[i] {\n\t\t\tcontinue\n\t\t}\n\t\tvehicle := &vehicles[i]\n\t\tif vehicle.ID == rebate.VehicleID &&',
)
text = text.replace(
    '\t\t\treturn vehicle\n\t\t}\n\t}\n\treturn nil\n}',
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
