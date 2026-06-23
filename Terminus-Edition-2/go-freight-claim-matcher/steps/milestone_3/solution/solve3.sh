#!/usr/bin/env bash
set -euo pipefail

cd /app

python3 <<'PY'
from pathlib import Path

path = Path("/app/cmd/reconcile/main.go")
text = path.read_text()

text = text.replace(
    "type Shipment struct {\n\tID       string\n\t// Admgount mirrors the carrier CSV column `admgount_id`; preserve this spelling.\n\tAdmgount string\n\tAmount   int\n\tStatus   string\n\tReason   string\n}",
    "type Shipment struct {\n\tID        string\n\t// Admgount mirrors the carrier CSV column `admgount_id`; preserve this spelling.\n\tAdmgount  string\n\tAmount    int\n\tStatus    string\n\tReason    string\n\tShipDate  string\n}",
)
text = text.replace(
    "type Claim struct {\n\tShipmentID string\n\t// Admgount mirrors the carrier CSV column `admgount_id`; preserve this spelling.\n\tAdmgount  string\n\tAmount    int\n\tReason    string\n}",
    "type Claim struct {\n\tShipmentID string\n\t// Admgount mirrors the carrier CSV column `admgount_id`; preserve this spelling.\n\tAdmgount   string\n\tAmount     int\n\tReason     string\n\tClaimDate  string\n}",
)
text = text.replace(
    "out = append(out, Shipment{ID: clean(row[0]), Admgount: clean(row[1]), Amount: amount, Status: strings.ToUpper(clean(row[3])), Reason: canonicalReason(row[4])})",
    '''shipDate := ""
\t\tif len(row) > 5 {
\t\t\tshipDate = clean(row[5])
\t\t}
\t\tout = append(out, Shipment{ID: clean(row[0]), Admgount: clean(row[1]), Amount: amount, Status: strings.ToUpper(clean(row[3])), Reason: canonicalReason(row[4]), ShipDate: shipDate})''',
)
text = text.replace(
    "out = append(out, Claim{ShipmentID: clean(row[0]), Admgount: clean(row[1]), Amount: amount, Reason: canonicalReason(row[3])})",
    '''claimDate := ""
\t\tif len(row) > 4 {
\t\t\tclaimDate = clean(row[4])
\t\t}
\t\tout = append(out, Claim{ShipmentID: clean(row[0]), Admgount: clean(row[1]), Amount: amount, Reason: canonicalReason(row[3]), ClaimDate: claimDate})''',
)
text = text.replace(
    "return writeOutputs(shipments, claims)",
    '''openDates, err := loadOpenDates("/app/config/cutoff_calendar.txt")
\tif err != nil {
\t\treturn err
\t}
\treturn writeOutputs(shipments, claims, openDates)''',
)
text = text.replace(
    "func writeOutputs(shipments []Shipment, claims []Claim) error {",
    "func writeOutputs(shipments []Shipment, claims []Claim, openDates map[string]bool) error {",
)
text = text.replace(
    "matchIndex := findMatch(shipments, claim, usedShipments)",
    "matchIndex := findMatch(shipments, claim, usedShipments, openDates)",
)
start = text.index("func findMatch(")
end = text.index("\nfunc clean(", start)
text = text[:start] + '''func findMatch(shipments []Shipment, claim Claim, used []bool, openDates map[string]bool) int {
\tbestIndex := -1
\tfor i := range shipments {
\t\tif used[i] {
\t\t\tcontinue
\t\t}
\t\tshipment := &shipments[i]
\t\tif !openDates[claim.ClaimDate] ||
\t\t\tclaim.ClaimDate == "" ||
\t\t\tshipment.ShipDate == "" ||
\t\t\tshipment.ShipDate > claim.ClaimDate ||
\t\t\tshipment.ID != claim.ShipmentID ||
\t\t\tshipment.Admgount != claim.Admgount ||
\t\t\tshipment.Amount != claim.Amount ||
\t\t\tshipment.Status != "POSTED" ||
\t\t\t!allowedReason(shipment.Reason) ||
\t\t\tshipment.Reason != claim.Reason {
\t\t\tcontinue
\t\t}
\t\tif bestIndex < 0 || shipment.ShipDate > shipments[bestIndex].ShipDate {
\t\t\tbestIndex = i
\t\t}
\t}
\treturn bestIndex
}

func loadOpenDates(path string) (map[string]bool, error) {
\tdata, err := os.ReadFile(path)
\tif err != nil {
\t\treturn nil, err
\t}
\topenDates := map[string]bool{}
\tfor _, line := range strings.Split(string(data), "\\n") {
\t\tfields := strings.Fields(line)
\t\tif len(fields) >= 2 && strings.EqualFold(fields[1], "open") {
\t\t\topenDates[fields[0]] = true
\t\t}
\t}
\treturn openDates, nil
}
''' + text[end:]

path.write_text(text)
PY

/app/scripts/run_batch.sh
test -s /app/out/claim_report.csv
test -s /app/out/claim_summary.json
