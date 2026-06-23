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
    'out = append(out, Membership{ID: row[0], Customer: row[1], Amount: amount, Status: row[3], Program: row[4]})',
    'out = append(out, Membership{ID: clean(row[0]), Customer: clean(row[1]), Amount: amount, Status: strings.ToUpper(clean(row[3])), Program: strings.ToUpper(clean(row[4]))})',
)
text = text.replace(
    'out = append(out, Refund{MembershipID: row[0], Customer: row[1], Amount: amount, Program: row[3]})',
    'out = append(out, Refund{MembershipID: clean(row[0]), Customer: clean(row[1]), Amount: amount, Program: strings.ToUpper(clean(row[3]))})',
)
text = text.replace(
    'summary.MatchedAmountCents -= refund.Amount',
    'summary.MatchedAmountCents += refund.Amount',
)
text = text.replace(
    'if len(membership.ID) >= 8 && len(refund.MembershipID) >= 8 &&\n\t\t\tmembership.ID[:8] == refund.MembershipID[:8] &&',
    'if membership.ID == refund.MembershipID &&',
)
text = text.replace(
    'return program == "ADULT" || program == "FAMILY" || program == "PATRON"',
    'return program == "ADULT" || program == "FAMILY" || program == "PATRON"',
)
text = text.replace(
    '\tsummary := Summary{}\n\tfor _, refund := range refunds {\n\t\tmatch := findMatch(memberships, refund)',
    '\tsummary := Summary{}\n\tusedMemberships := make([]bool, len(memberships))\n\tfor _, refund := range refunds {\n\t\tmatchIndex := findMatch(memberships, refund, usedMemberships)\n\t\tvar match *Membership\n\t\tif matchIndex >= 0 {\n\t\t\tmatch = &memberships[matchIndex]\n\t\t\tusedMemberships[matchIndex] = true\n\t\t}',
)
text = text.replace(
    'func findMatch(memberships []Membership, refund Refund) *Membership {\n\tfor i := range memberships {\n\t\tmembership := &memberships[i]\n\t\tif membership.ID == refund.MembershipID &&',
    'func findMatch(memberships []Membership, refund Refund, used []bool) int {\n\tfor i := range memberships {\n\t\tif used[i] {\n\t\t\tcontinue\n\t\t}\n\t\tmembership := &memberships[i]\n\t\tif membership.ID == refund.MembershipID &&',
)
text = text.replace(
    '\t\t\treturn membership\n\t\t}\n\t}\n\treturn nil\n}',
    '\t\t\treturn i\n\t\t}\n\t}\n\treturn -1\n}',
)
text = text.replace(
    'func allowedProgram(program string) bool {\n\treturn program == "ADULT" || program == "FAMILY" || program == "PATRON"\n}',
    'func clean(value string) string {\n\treturn strings.TrimSpace(value)\n}\n\nfunc allowedProgram(program string) bool {\n\tprogram = strings.ToUpper(clean(program))\n\treturn program == "ADULT" || program == "FAMILY" || program == "PATRON"\n}',
)
path.write_text(text)
PY

/app/scripts/run_batch.sh
test -s /app/out/refund_report.csv
test -s /app/out/refund_summary.json
