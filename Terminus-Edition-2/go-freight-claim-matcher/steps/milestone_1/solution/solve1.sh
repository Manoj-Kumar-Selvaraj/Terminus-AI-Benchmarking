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
    'out = append(out, Shipment{ID: row[0], Admgount: row[1], Amount: amount, Status: row[3], Reason: row[4]})',
    'out = append(out, Shipment{ID: clean(row[0]), Admgount: clean(row[1]), Amount: amount, Status: strings.ToUpper(clean(row[3])), Reason: strings.ToUpper(clean(row[4]))})',
)
text = text.replace(
    'out = append(out, Claim{ShipmentID: row[0], Admgount: row[1], Amount: amount, Reason: row[3]})',
    'out = append(out, Claim{ShipmentID: clean(row[0]), Admgount: clean(row[1]), Amount: amount, Reason: strings.ToUpper(clean(row[3]))})',
)
text = text.replace(
    'summary.MatchedAmountCents -= claim.Amount',
    'summary.MatchedAmountCents += claim.Amount',
)
text = text.replace(
    'if len(shipment.ID) >= 8 && len(claim.ShipmentID) >= 8 &&\n\t\t\tshipment.ID[:8] == claim.ShipmentID[:8] &&',
    'if shipment.ID == claim.ShipmentID &&',
)
text = text.replace(
    'return reason == "DAMAGED" || reason == "HAZ"',
    'return reason == "DAMAGED" || reason == "LOST" || reason == "HAZ"',
)
text = text.replace(
    '\tsummary := Summary{}\n\tfor _, claim := range claims {\n\t\tmatch := findMatch(shipments, claim)',
    '\tsummary := Summary{}\n\tusedShipments := make([]bool, len(shipments))\n\tfor _, claim := range claims {\n\t\tmatchIndex := findMatch(shipments, claim, usedShipments)\n\t\tvar match *Shipment\n\t\tif matchIndex >= 0 {\n\t\t\tmatch = &shipments[matchIndex]\n\t\t\tusedShipments[matchIndex] = true\n\t\t}',
)
text = text.replace(
    'func findMatch(shipments []Shipment, claim Claim) *Shipment {\n\tfor i := range shipments {\n\t\tshipment := &shipments[i]\n\t\tif shipment.ID == claim.ShipmentID &&',
    'func findMatch(shipments []Shipment, claim Claim, used []bool) int {\n\tfor i := range shipments {\n\t\tif used[i] {\n\t\t\tcontinue\n\t\t}\n\t\tshipment := &shipments[i]\n\t\tif shipment.ID == claim.ShipmentID &&',
)
text = text.replace(
    '\t\t\treturn shipment\n\t\t}\n\t}\n\treturn nil\n}',
    '\t\t\treturn i\n\t\t}\n\t}\n\treturn -1\n}',
)
text = text.replace(
    'func allowedReason(reason string) bool {\n\treturn reason == "DAMAGED" || reason == "LOST" || reason == "HAZ"\n}',
    'func clean(value string) string {\n\treturn strings.TrimSpace(value)\n}\n\nfunc allowedReason(reason string) bool {\n\treason = strings.ToUpper(clean(reason))\n\treturn reason == "DAMAGED" || reason == "LOST" || reason == "HAZ"\n}',
)
required_patches = {
    "strings import": '"strconv"\n\t"strings"',
    "positive matched total": "summary.MatchedAmountCents += claim.Amount",
    "full shipment id match": "if shipment.ID == claim.ShipmentID &&",
    "one-use shipment tracking": "usedShipments := make([]bool, len(shipments))",
    "indexed findMatch": "func findMatch(shipments []Shipment, claim Claim, used []bool) int",
    "LOST allowed reason": 'return reason == "DAMAGED" || reason == "LOST" || reason == "HAZ"',
    "clean helper": "func clean(value string) string",
}
for label, needle in required_patches.items():
    if needle not in text:
        raise SystemExit(f"patch failed: {label} not applied")
path.write_text(text)
PY

/app/scripts/run_batch.sh
test -s /app/out/claim_report.csv
test -s /app/out/claim_summary.json
