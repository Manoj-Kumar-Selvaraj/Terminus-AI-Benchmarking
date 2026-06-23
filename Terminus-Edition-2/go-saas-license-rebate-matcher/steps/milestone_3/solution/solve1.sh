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
    'out = append(out, License{ID: row[0], Tenant: row[1], Amount: amount, Status: row[3], Tier: row[4]})',
    'out = append(out, License{ID: clean(row[0]), Tenant: clean(row[1]), Amount: amount, Status: strings.ToUpper(clean(row[3])), Tier: strings.ToUpper(clean(row[4]))})',
)
text = text.replace(
    'out = append(out, Rebate{LicenseID: row[0], Tenant: row[1], Amount: amount, Tier: row[3]})',
    'out = append(out, Rebate{LicenseID: clean(row[0]), Tenant: clean(row[1]), Amount: amount, Tier: strings.ToUpper(clean(row[3]))})',
)
text = text.replace(
    'summary.MatchedAmountCents -= rebate.Amount',
    'summary.MatchedAmountCents += rebate.Amount',
)
text = text.replace(
    'if len(license.ID) >= 8 && len(rebate.LicenseID) >= 8 &&\n\t\t\tlicense.ID[:8] == rebate.LicenseID[:8] &&',
    'if license.ID == rebate.LicenseID &&',
)
text = text.replace(
    'return tier == "STARTER" || tier == "BUSINESS" || tier == "ENTERPRISE"',
    'return tier == "STARTER" || tier == "BUSINESS" || tier == "ENTERPRISE"',
)
text = text.replace(
    '\tsummary := Summary{}\n\tfor _, rebate := range rebates {\n\t\tmatch := findMatch(licenses, rebate)',
    '\tsummary := Summary{}\n\tusedLicenses := make([]bool, len(licenses))\n\tfor _, rebate := range rebates {\n\t\tmatchIndex := findMatch(licenses, rebate, usedLicenses)\n\t\tvar match *License\n\t\tif matchIndex >= 0 {\n\t\t\tmatch = &licenses[matchIndex]\n\t\t\tusedLicenses[matchIndex] = true\n\t\t}',
)
text = text.replace(
    'func findMatch(licenses []License, rebate Rebate) *License {\n\tfor i := range licenses {\n\t\tlicense := &licenses[i]\n\t\tif license.ID == rebate.LicenseID &&',
    'func findMatch(licenses []License, rebate Rebate, used []bool) int {\n\tfor i := range licenses {\n\t\tif used[i] {\n\t\t\tcontinue\n\t\t}\n\t\tlicense := &licenses[i]\n\t\tif license.ID == rebate.LicenseID &&',
)
text = text.replace(
    '\t\t\treturn license\n\t\t}\n\t}\n\treturn nil\n}',
    '\t\t\treturn i\n\t\t}\n\t}\n\treturn -1\n}',
)
text = text.replace(
    'func allowedTier(tier string) bool {\n\treturn tier == "STARTER" || tier == "BUSINESS" || tier == "ENTERPRISE"\n}',
    'func clean(value string) string {\n\treturn strings.TrimSpace(value)\n}\n\nfunc allowedTier(tier string) bool {\n\ttier = strings.ToUpper(clean(tier))\n\treturn tier == "STARTER" || tier == "BUSINESS" || tier == "ENTERPRISE"\n}',
)
path.write_text(text)
PY

/app/scripts/run_batch.sh
test -s /app/out/rebate_report.csv
test -s /app/out/rebate_summary.json
