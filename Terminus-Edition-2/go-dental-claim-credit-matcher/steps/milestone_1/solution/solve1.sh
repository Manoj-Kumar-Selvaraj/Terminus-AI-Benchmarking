#!/usr/bin/env bash
set -euo pipefail

cd /app

python3 <<'PY'
from pathlib import Path

path = Path("/app/cmd/reconcile/main.go")
text = path.read_text()
if "func clean(value string)" in text:
    raise SystemExit(0)
if '"strings"' not in text:
    text = text.replace('"strconv"', '"strconv"\n\t"strings"')
text = text.replace('amount, err := strconv.Atoi(row[2])', 'amount, err := strconv.Atoi(clean(row[2]))')
text = text.replace(
    'out = append(out, Claim{ID: row[0], Patient: row[1], Amount: amount, Status: row[3], Procedure: row[4]})',
    'out = append(out, Claim{ID: clean(row[0]), Patient: clean(row[1]), Amount: amount, Status: strings.ToUpper(clean(row[3])), Procedure: strings.ToUpper(clean(row[4]))})',
)
text = text.replace(
    'out = append(out, Credit{ClaimID: row[0], Patient: row[1], Amount: amount, Procedure: row[3]})',
    'out = append(out, Credit{ClaimID: clean(row[0]), Patient: clean(row[1]), Amount: amount, Procedure: strings.ToUpper(clean(row[3]))})',
)
text = text.replace(
    'summary.MatchedAmountCents -= credit.Amount',
    'summary.MatchedAmountCents += credit.Amount',
)
text = text.replace(
    'if len(claim.ID) >= 8 && len(credit.ClaimID) >= 8 &&\n\t\t\tclaim.ID[:8] == credit.ClaimID[:8] &&',
    'if claim.ID == credit.ClaimID &&',
)
text = text.replace(
    'return procedure == "PREVENTIVE" || procedure == "RESTORATIVE" || procedure == "ORTHO"',
    'return procedure == "PREVENTIVE" || procedure == "RESTORATIVE" || procedure == "ORTHO"',
)
text = text.replace(
    '\tsummary := Summary{}\n\tfor _, credit := range credits {\n\t\tmatch := findMatch(claims, credit)',
    '\tsummary := Summary{}\n\tusedClaims := make([]bool, len(claims))\n\tfor _, credit := range credits {\n\t\tmatchIndex := findMatch(claims, credit, usedClaims)\n\t\tvar match *Claim\n\t\tif matchIndex >= 0 {\n\t\t\tmatch = &claims[matchIndex]\n\t\t\tusedClaims[matchIndex] = true\n\t\t}',
)
text = text.replace(
    'func findMatch(claims []Claim, credit Credit) *Claim {\n\tfor i := range claims {\n\t\tclaim := &claims[i]\n\t\tif claim.ID == credit.ClaimID &&',
    'func findMatch(claims []Claim, credit Credit, used []bool) int {\n\tfor i := range claims {\n\t\tif used[i] {\n\t\t\tcontinue\n\t\t}\n\t\tclaim := &claims[i]\n\t\tif claim.ID == credit.ClaimID &&',
)
text = text.replace(
    '\t\t\treturn claim\n\t\t}\n\t}\n\treturn nil\n}',
    '\t\t\treturn i\n\t\t}\n\t}\n\treturn -1\n}',
)
text = text.replace(
    'func allowedProcedure(procedure string) bool {\n\treturn procedure == "PREVENTIVE" || procedure == "RESTORATIVE" || procedure == "ORTHO"\n}',
    'func clean(value string) string {\n\treturn strings.TrimSpace(value)\n}\n\nfunc allowedProcedure(procedure string) bool {\n\tprocedure = strings.ToUpper(clean(procedure))\n\treturn procedure == "PREVENTIVE" || procedure == "RESTORATIVE" || procedure == "ORTHO"\n}',
)
path.write_text(text)
PY

/app/scripts/run_batch.sh
test -s /app/out/credit_report.csv
test -s /app/out/credit_summary.json
