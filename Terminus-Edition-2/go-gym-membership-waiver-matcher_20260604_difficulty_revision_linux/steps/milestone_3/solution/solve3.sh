#!/usr/bin/env bash
set -euo pipefail

cd /app

python3 <<'PY'
from pathlib import Path

path = Path("/app/cmd/reconcile/main.go")
text = path.read_text()

text = text.replace(
    "type Membership struct {\n\tID       string\n\tCustomer string\n\tAmount   int\n\tStatus   string\n\tPlan   string\n}",
    "type Membership struct {\n\tID       string\n\tCustomer string\n\tAmount   int\n\tStatus   string\n\tPlan  string\n\tRenewalDate  string\n}",
)
text = text.replace(
    "type Waiver struct {\n\tMembershipID string\n\tCustomer  string\n\tAmount    int\n\tPlan    string\n}",
    "type Waiver struct {\n\tMembershipID     string\n\tCustomer   string\n\tAmount     int\n\tPlan    string\n\tWaiverDate string\n}",
)
text = text.replace(
    "out = append(out, Membership{ID: clean(row[0]), Customer: clean(row[1]), Amount: amount, Status: strings.ToUpper(clean(row[3])), Plan: canonicalPlan(row[4])})",
    '''dueDate := ""
\t\tif len(row) > 5 {
\t\t\tdueDate = clean(row[5])
\t\t}
\t\tout = append(out, Membership{ID: clean(row[0]), Customer: clean(row[1]), Amount: amount, Status: strings.ToUpper(clean(row[3])), Plan: canonicalPlan(row[4]), RenewalDate: dueDate})''',
)
text = text.replace(
    "out = append(out, Waiver{MembershipID: clean(row[0]), Customer: clean(row[1]), Amount: amount, Plan: canonicalPlan(row[3])})",
    '''waiverDate := ""
\t\tif len(row) > 4 {
\t\t\twaiverDate = clean(row[4])
\t\t}
\t\tout = append(out, Waiver{MembershipID: clean(row[0]), Customer: clean(row[1]), Amount: amount, Plan: canonicalPlan(row[3]), WaiverDate: waiverDate})''',
)
text = text.replace(
    "return writeOutputs(memberships, waivers)",
    '''openDates, err := loadOpenDates("/app/config/cutoff_calendar.txt")
\tif err != nil {
\t\treturn err
\t}
\treturn writeOutputs(memberships, waivers, openDates)''',
)
text = text.replace(
    "func writeOutputs(memberships []Membership, waivers []Waiver) error {",
    "func writeOutputs(memberships []Membership, waivers []Waiver, openDates map[string]bool) error {",
)
text = text.replace(
    "matchIndex := findMatch(memberships, waiver, usedMemberships)",
    "matchIndex := findMatch(memberships, waiver, usedMemberships, openDates)",
)
start = text.index("func findMatch(")
end = text.index("\nfunc clean(", start)
text = text[:start] + '''func findMatch(memberships []Membership, waiver Waiver, used []bool, openDates map[string]bool) int {
\tbestIndex := -1
\tfor i := range memberships {
\t\tif used[i] {
\t\t\tcontinue
\t\t}
\t\tmembership := &memberships[i]
\t\tif !openDates[waiver.WaiverDate] ||
\t\t\twaiver.WaiverDate == "" ||
\t\t\tmembership.RenewalDate == "" ||
\t\t\twaiver.WaiverDate > membership.RenewalDate ||
\t\t\tmembership.ID != waiver.MembershipID ||
\t\t\tmembership.Customer != waiver.Customer ||
\t\t\tmembership.Amount != waiver.Amount ||
\t\t\tmembership.Status != "ACTIVE" ||
\t\t\t!allowedPlan(membership.Plan) ||
\t\t\tmembership.Plan != waiver.Plan {
\t\t\tcontinue
\t\t}
\t\tif bestIndex < 0 || membership.RenewalDate > memberships[bestIndex].RenewalDate {
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
test -s /app/out/waiver_report.csv
test -s /app/out/waiver_summary.json
