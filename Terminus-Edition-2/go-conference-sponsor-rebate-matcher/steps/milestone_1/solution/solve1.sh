#!/usr/bin/env bash
set -euo pipefail

cd /app

if grep -q 'usedSponsorships' /app/cmd/reconcile/main.go; then
  /app/scripts/run_batch.sh
  test -s /app/out/rebate_report.csv
  test -s /app/out/rebate_summary.json
  exit 0
fi

python3 <<'PY'
from pathlib import Path

path = Path("/app/cmd/reconcile/main.go")
text = path.read_text()
text = text.replace('"strconv"', '"strconv"\n\t"strings"')
text = text.replace('amount, err := strconv.Atoi(row[2])', 'amount, err := strconv.Atoi(clean(row[2]))')
text = text.replace(
    'out = append(out, Sponsorship{ID: row[0], Customer: row[1], Amount: amount, Status: row[3], Level: row[4]})',
    'out = append(out, Sponsorship{ID: clean(row[0]), Customer: clean(row[1]), Amount: amount, Status: strings.ToUpper(clean(row[3])), Level: strings.ToUpper(clean(row[4]))})',
)
text = text.replace(
    'out = append(out, Rebate{SponsorshipID: row[0], Customer: row[1], Amount: amount, Level: row[3]})',
    'out = append(out, Rebate{SponsorshipID: clean(row[0]), Customer: clean(row[1]), Amount: amount, Level: strings.ToUpper(clean(row[3]))})',
)
text = text.replace(
    'summary.MatchedAmountCents -= rebate.Amount',
    'summary.MatchedAmountCents += rebate.Amount',
)
text = text.replace(
    'if len(sponsorship.ID) >= 8 && len(rebate.SponsorshipID) >= 8 &&\n\t\t\tsponsorship.ID[:8] == rebate.SponsorshipID[:8] &&',
    'if sponsorship.ID == rebate.SponsorshipID &&',
)
text = text.replace(
    'return level == "BRONZE" || level == "GOLD" || level == "PLATINUM"',
    'return level == "BRONZE" || level == "GOLD" || level == "PLATINUM"',
)
text = text.replace(
    '\tsummary := Summary{}\n\tfor _, rebate := range rebates {\n\t\tmatch := findMatch(sponsorships, rebate)',
    '\tsummary := Summary{}\n\tusedSponsorships := make([]bool, len(sponsorships))\n\tfor _, rebate := range rebates {\n\t\tmatchIndex := findMatch(sponsorships, rebate, usedSponsorships)\n\t\tvar match *Sponsorship\n\t\tif matchIndex >= 0 {\n\t\t\tmatch = &sponsorships[matchIndex]\n\t\t\tusedSponsorships[matchIndex] = true\n\t\t}',
)
text = text.replace(
    'func findMatch(sponsorships []Sponsorship, rebate Rebate) *Sponsorship {\n\tfor i := range sponsorships {\n\t\tsponsorship := &sponsorships[i]\n\t\tif sponsorship.ID == rebate.SponsorshipID &&',
    'func findMatch(sponsorships []Sponsorship, rebate Rebate, used []bool) int {\n\tfor i := range sponsorships {\n\t\tif used[i] {\n\t\t\tcontinue\n\t\t}\n\t\tsponsorship := &sponsorships[i]\n\t\tif sponsorship.ID == rebate.SponsorshipID &&',
)
text = text.replace(
    '\t\t\treturn sponsorship\n\t\t}\n\t}\n\treturn nil\n}',
    '\t\t\treturn i\n\t\t}\n\t}\n\treturn -1\n}',
)
text = text.replace(
    'func allowedLevel(level string) bool {\n\treturn level == "BRONZE" || level == "GOLD" || level == "PLATINUM"\n}',
    'func clean(value string) string {\n\treturn strings.TrimSpace(value)\n}\n\nfunc allowedLevel(level string) bool {\n\tlevel = strings.ToUpper(clean(level))\n\treturn level == "BRONZE" || level == "GOLD" || level == "PLATINUM"\n}',
)
path.write_text(text)
PY

/app/scripts/run_batch.sh
test -s /app/out/rebate_report.csv
test -s /app/out/rebate_summary.json
