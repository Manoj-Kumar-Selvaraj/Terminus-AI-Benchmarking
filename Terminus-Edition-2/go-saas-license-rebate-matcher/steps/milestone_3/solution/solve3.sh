#!/usr/bin/env bash
set -euo pipefail

cd /app

python3 <<'PY'
from pathlib import Path

path = Path("/app/cmd/reconcile/main.go")
text = path.read_text()

text = text.replace(
    "type License struct {\n\tID       string\n\tTenant string\n\tAmount   int\n\tStatus   string\n\tTier   string\n}",
    "type License struct {\n\tID       string\n\tTenant string\n\tAmount   int\n\tStatus   string\n\tTier  string\n\tLicenseEnd  string\n}",
)
text = text.replace(
    "type Rebate struct {\n\tLicenseID string\n\tTenant  string\n\tAmount    int\n\tTier    string\n}",
    "type Rebate struct {\n\tLicenseID     string\n\tTenant   string\n\tAmount     int\n\tTier    string\n\tRebateDate string\n}",
)
text = text.replace(
    "out = append(out, License{ID: clean(row[0]), Tenant: clean(row[1]), Amount: amount, Status: strings.ToUpper(clean(row[3])), Tier: canonicalTier(row[4])})",
    '''dueDate := ""
\t\tif len(row) > 5 {
\t\t\tdueDate = clean(row[5])
\t\t}
\t\tout = append(out, License{ID: clean(row[0]), Tenant: clean(row[1]), Amount: amount, Status: strings.ToUpper(clean(row[3])), Tier: canonicalTier(row[4]), LicenseEnd: dueDate})''',
)
text = text.replace(
    "out = append(out, Rebate{LicenseID: clean(row[0]), Tenant: clean(row[1]), Amount: amount, Tier: canonicalTier(row[3])})",
    '''rebateDate := ""
\t\tif len(row) > 4 {
\t\t\trebateDate = clean(row[4])
\t\t}
\t\tout = append(out, Rebate{LicenseID: clean(row[0]), Tenant: clean(row[1]), Amount: amount, Tier: canonicalTier(row[3]), RebateDate: rebateDate})''',
)
text = text.replace(
    "return writeOutputs(licenses, rebates)",
    '''openDates, err := loadOpenDates("/app/config/cutoff_calendar.txt")
\tif err != nil {
\t\treturn err
\t}
\treturn writeOutputs(licenses, rebates, openDates)''',
)
text = text.replace(
    "func writeOutputs(licenses []License, rebates []Rebate) error {",
    "func writeOutputs(licenses []License, rebates []Rebate, openDates map[string]bool) error {",
)
text = text.replace(
    "matchIndex := findMatch(licenses, rebate, usedLicenses)",
    "matchIndex := findMatch(licenses, rebate, usedLicenses, openDates)",
)
start = text.index("func findMatch(")
end = text.index("\nfunc clean(", start)
text = text[:start] + '''func findMatch(licenses []License, rebate Rebate, used []bool, openDates map[string]bool) int {
\tbestIndex := -1
\tfor i := range licenses {
\t\tif used[i] {
\t\t\tcontinue
\t\t}
\t\tlicense := &licenses[i]
\t\tif !openDates[rebate.RebateDate] ||
\t\t\trebate.RebateDate == "" ||
\t\t\tlicense.LicenseEnd == "" ||
\t\t\trebate.RebateDate > license.LicenseEnd ||
\t\t\tlicense.ID != rebate.LicenseID ||
\t\t\tlicense.Tenant != rebate.Tenant ||
\t\t\tlicense.Amount != rebate.Amount ||
\t\t\tlicense.Status != "LICENSED" ||
\t\t\t!allowedTier(license.Tier) ||
\t\t\tlicense.Tier != rebate.Tier {
\t\t\tcontinue
\t\t}
\t\tif bestIndex < 0 || license.LicenseEnd > licenses[bestIndex].LicenseEnd {
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
test -s /app/out/rebate_report.csv
test -s /app/out/rebate_summary.json
