#!/usr/bin/env bash
set -euo pipefail

cd /app

python3 <<'PY'
from pathlib import Path

path = Path("/app/cmd/reconcile/main.go")
text = path.read_text()

text = text.replace(
    "type Membership struct {\n\tID       string\n\tCustomer string\n\tAmount   int\n\tStatus   string\n\tProgram   string\n}",
    "type Membership struct {\n\tID       string\n\tCustomer string\n\tAmount   int\n\tStatus   string\n\tProgram  string\n\tValidThrough  string\n}",
)
text = text.replace(
    "type Refund struct {\n\tMembershipID string\n\tCustomer  string\n\tAmount    int\n\tProgram    string\n}",
    "type Refund struct {\n\tMembershipID     string\n\tCustomer   string\n\tAmount     int\n\tProgram    string\n\tRefundDate string\n}",
)
text = text.replace(
    "out = append(out, Membership{ID: clean(row[0]), Customer: clean(row[1]), Amount: amount, Status: strings.ToUpper(clean(row[3])), Program: canonicalProgram(row[4])})",
    '''dueDate := ""
\t\tif len(row) > 5 {
\t\t\tdueDate = clean(row[5])
\t\t}
\t\tout = append(out, Membership{ID: clean(row[0]), Customer: clean(row[1]), Amount: amount, Status: strings.ToUpper(clean(row[3])), Program: canonicalProgram(row[4]), ValidThrough: dueDate})''',
)
text = text.replace(
    "out = append(out, Refund{MembershipID: clean(row[0]), Customer: clean(row[1]), Amount: amount, Program: canonicalProgram(row[3])})",
    '''refundDate := ""
\t\tif len(row) > 4 {
\t\t\trefundDate = clean(row[4])
\t\t}
\t\tout = append(out, Refund{MembershipID: clean(row[0]), Customer: clean(row[1]), Amount: amount, Program: canonicalProgram(row[3]), RefundDate: refundDate})''',
)
text = text.replace(
    "return writeOutputs(memberships, refunds)",
    '''openDates, err := loadOpenDates("/app/config/cutoff_calendar.txt")
\tif err != nil {
\t\treturn err
\t}
\treturn writeOutputs(memberships, refunds, openDates)''',
)
text = text.replace(
    "func writeOutputs(memberships []Membership, refunds []Refund) error {",
    "func writeOutputs(memberships []Membership, refunds []Refund, openDates map[string]bool) error {",
)
text = text.replace(
    "matchIndex := findMatch(memberships, refund, usedMemberships)",
    "matchIndex := findMatch(memberships, refund, usedMemberships, openDates)",
)
start = text.index("func findMatch(")
end = text.index("\nfunc clean(", start)
text = text[:start] + '''func findMatch(memberships []Membership, refund Refund, used []bool, openDates map[string]bool) int {
\tbestIndex := -1
\tfor i := range memberships {
\t\tif used[i] {
\t\t\tcontinue
\t\t}
\t\tmembership := &memberships[i]
\t\tif !openDates[refund.RefundDate] ||
\t\t\trefund.RefundDate == "" ||
\t\t\tmembership.ValidThrough == "" ||
\t\t\trefund.RefundDate > membership.ValidThrough ||
\t\t\tmembership.ID != refund.MembershipID ||
\t\t\tmembership.Customer != refund.Customer ||
\t\t\tmembership.Amount != refund.Amount ||
\t\t\tmembership.Status != "ACTIVE" ||
\t\t\t!allowedProgram(membership.Program) ||
\t\t\tmembership.Program != refund.Program {
\t\t\tcontinue
\t\t}
\t\tif bestIndex < 0 || membership.ValidThrough > memberships[bestIndex].ValidThrough {
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
test -s /app/out/refund_report.csv
test -s /app/out/refund_summary.json
