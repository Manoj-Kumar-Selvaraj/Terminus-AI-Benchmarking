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
    'return plan == "BASIC" || plan == "PLUS" || plan == "ELITE"',
    'return plan == "BASIC" || plan == "PLUS" || plan == "ELITE"',
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

/app/scripts/run_batch.sh
test -s /app/out/waiver_report.csv
test -s /app/out/waiver_summary.json
