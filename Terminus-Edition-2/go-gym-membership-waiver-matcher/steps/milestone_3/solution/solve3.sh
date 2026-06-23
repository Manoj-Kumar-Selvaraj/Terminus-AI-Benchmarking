#!/usr/bin/env bash
set -euo pipefail

cd /app

if grep -q 'func loadOpenDates' /app/cmd/reconcile/main.go && grep -q 'RenewalDate string' /app/cmd/reconcile/main.go; then
  /app/scripts/run_batch.sh
  test -s /app/out/waiver_report.csv
  test -s /app/out/waiver_summary.json
  exit 0
fi

if ! grep -q 'usedMemberships' /app/cmd/reconcile/main.go; then
python3 <<'PY'
from pathlib import Path

path = Path("/app/cmd/reconcile/main.go")
text = path.read_text()
if '"strings"' not in text:
    text = text.replace('"strconv"', '"strconv"\n\t"strings"')
text = text.replace('amount, err := strconv.Atoi(row[2])', 'amount, err := strconv.Atoi(clean(row[2]))')
text = text.replace(
    'out = append(out, Membership{ID: row[0], Customer: row[1], Amount: amount, Status: row[3], Plan: row[4]})',
    'out = append(out, Membership{ID: clean(row[0]), Customer: clean(row[1]), Amount: amount, Status: strings.ToUpper(clean(row[3])), Plan: strings.ToUpper(clean(row[4]))})',
)
text = text.replace(
    'out = append(out, Waiver{MembershipID: row[0], Customer: row[1], Amount: amount, Plan: row[3]})',
    'out = append(out, Waiver{MembershipID: clean(row[0]), Customer: clean(row[1]), Amount: amount, Plan: strings.ToUpper(clean(row[3]))})',
)
text = text.replace(
    'summary.MatchedAmountCents -= waiver.Amount',
    'summary.MatchedAmountCents += waiver.Amount',
)
text = text.replace(
    'if len(membership.ID) >= 8 && len(waiver.MembershipID) >= 8 &&\n\t\t\tmembership.ID[:8] == waiver.MembershipID[:8] &&',
    'if membership.ID == waiver.MembershipID &&',
)
text = text.replace(
    '\tsummary := Summary{}\n\tfor _, waiver := range waivers {\n\t\tmatch := findMatch(memberships, waiver)',
    '\tsummary := Summary{}\n\tusedMemberships := make([]bool, len(memberships))\n\tfor _, waiver := range waivers {\n\t\tmatchIndex := findMatch(memberships, waiver, usedMemberships)\n\t\tvar match *Membership\n\t\tif matchIndex >= 0 {\n\t\t\tmatch = &memberships[matchIndex]\n\t\t\tusedMemberships[matchIndex] = true\n\t\t}',
)
text = text.replace(
    'func findMatch(memberships []Membership, waiver Waiver) *Membership {\n\tfor i := range memberships {\n\t\tmembership := &memberships[i]\n\t\tif membership.ID == waiver.MembershipID &&',
    'func findMatch(memberships []Membership, waiver Waiver, used []bool) int {\n\tfor i := range memberships {\n\t\tif used[i] {\n\t\t\tcontinue\n\t\t}\n\t\tmembership := &memberships[i]\n\t\tif membership.ID == waiver.MembershipID &&',
)
text = text.replace(
    '\t\t\treturn membership\n\t\t}\n\t}\n\treturn nil\n}',
    '\t\t\treturn i\n\t\t}\n\t}\n\treturn -1\n}',
)
text = text.replace(
    'func allowedPlan(plan string) bool {\n\treturn plan == "BASIC" || plan == "PLUS" || plan == "ELITE"\n}',
    'func clean(value string) string {\n\treturn strings.TrimSpace(value)\n}\n\nfunc allowedPlan(plan string) bool {\n\tplan = strings.ToUpper(clean(plan))\n\treturn plan == "BASIC" || plan == "PLUS" || plan == "ELITE"\n}',
)
path.write_text(text)
PY
fi

if ! grep -q 'func canonicalPlan' /app/cmd/reconcile/main.go; then
python3 <<'PY'
from pathlib import Path

path = Path("/app/cmd/reconcile/main.go")
text = path.read_text()

text = text.replace(
    "Plan: strings.ToUpper(clean(row[4]))",
    "Plan: canonicalPlan(row[4])",
)
text = text.replace(
    "Plan: strings.ToUpper(clean(row[3]))",
    "Plan: canonicalPlan(row[3])",
)
text = text.replace(
    'func clean(value string) string {\n\treturn strings.TrimSpace(value)\n}\n\nfunc allowedPlan(plan string) bool {\n\tplan = strings.ToUpper(clean(plan))\n\treturn plan == "BASIC" || plan == "PLUS" || plan == "ELITE"\n}',
    '''func clean(value string) string {
\treturn strings.TrimSpace(value)
}

func canonicalPlan(plan string) string {
\tswitch strings.ToUpper(clean(plan)) {
\tcase "BAS":
\t\treturn "BASIC"
\tcase "PLU":
\t\treturn "PLUS"
\tcase "ELI":
\t\treturn "ELITE"
\tdefault:
\t\treturn strings.ToUpper(clean(plan))
\t}
}

func allowedPlan(plan string) bool {
\tplan = canonicalPlan(plan)
\treturn plan == "BASIC" || plan == "PLUS" || plan == "ELITE"
}''',
)

path.write_text(text)
PY
fi

python3 <<'PY'
from pathlib import Path

path = Path("/app/cmd/reconcile/main.go")
text = path.read_text()

text = text.replace(
    "type Membership struct {\n\tID       string\n\tCustomer string\n\tAmount   int\n\tStatus   string\n\tPlan   string\n}",
    "type Membership struct {\n\tID          string\n\tCustomer    string\n\tAmount      int\n\tStatus      string\n\tPlan        string\n\tRenewalDate string\n}",
)
text = text.replace(
    "type Waiver struct {\n\tMembershipID string\n\tCustomer  string\n\tAmount    int\n\tPlan    string\n}",
    "type Waiver struct {\n\tMembershipID string\n\tCustomer     string\n\tAmount       int\n\tPlan         string\n\tWaiverDate   string\n}",
)
text = text.replace(
    "out = append(out, Membership{ID: clean(row[0]), Customer: clean(row[1]), Amount: amount, Status: strings.ToUpper(clean(row[3])), Plan: canonicalPlan(row[4])})",
    '''renewalDate := ""
\t\tif len(row) > 5 {
\t\t\trenewalDate = clean(row[5])
\t\t}
\t\tout = append(out, Membership{ID: clean(row[0]), Customer: clean(row[1]), Amount: amount, Status: strings.ToUpper(clean(row[3])), Plan: canonicalPlan(row[4]), RenewalDate: renewalDate})''',
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
\t\tif bestIndex < 0 ||
\t\t\tmembership.RenewalDate > memberships[bestIndex].RenewalDate ||
\t\t\t(membership.RenewalDate == memberships[bestIndex].RenewalDate && i < bestIndex) {
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
