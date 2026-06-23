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
    'out = append(out, Account{ID: row[0], Customer: row[1], Amount: amount, Status: row[3], Channel: row[4]})',
    'out = append(out, Account{ID: clean(row[0]), Customer: clean(row[1]), Amount: amount, Status: strings.ToUpper(clean(row[3])), Channel: strings.ToUpper(clean(row[4]))})',
)
text = text.replace(
    'out = append(out, Reimbursement{AccountID: row[0], Customer: row[1], Amount: amount, Channel: row[3]})',
    'out = append(out, Reimbursement{AccountID: clean(row[0]), Customer: clean(row[1]), Amount: amount, Channel: strings.ToUpper(clean(row[3]))})',
)
text = text.replace(
    'summary.MatchedAmountCents -= reimbursement.Amount',
    'summary.MatchedAmountCents += reimbursement.Amount',
)
text = text.replace(
    'if len(account.ID) >= 8 && len(reimbursement.AccountID) >= 8 &&\n\t\t\taccount.ID[:8] == reimbursement.AccountID[:8] &&',
    'if account.ID == reimbursement.AccountID &&',
)
text = text.replace(
    'return channel == "ACH" || channel == "WIRE"',
    'return channel == "ACH" || channel == "CARD" || channel == "WIRE"',
)
text = text.replace(
    '\tsummary := Summary{}\n\tfor _, reimbursement := range reimbursements {\n\t\tmatch := findMatch(accounts, reimbursement)',
    '\tsummary := Summary{}\n\tusedAccounts := make([]bool, len(accounts))\n\tfor _, reimbursement := range reimbursements {\n\t\tmatchIndex := findMatch(accounts, reimbursement, usedAccounts)\n\t\tvar match *Account\n\t\tif matchIndex >= 0 {\n\t\t\tmatch = &accounts[matchIndex]\n\t\t\tusedAccounts[matchIndex] = true\n\t\t}',
)
text = text.replace(
    'func findMatch(accounts []Account, reimbursement Reimbursement) *Account {\n\tfor i := range accounts {\n\t\taccount := &accounts[i]\n\t\tif account.ID == reimbursement.AccountID &&',
    'func findMatch(accounts []Account, reimbursement Reimbursement, used []bool) int {\n\tfor i := range accounts {\n\t\tif used[i] {\n\t\t\tcontinue\n\t\t}\n\t\taccount := &accounts[i]\n\t\tif account.ID == reimbursement.AccountID &&',
)
text = text.replace(
    '\t\t\treturn account\n\t\t}\n\t}\n\treturn nil\n}',
    '\t\t\treturn i\n\t\t}\n\t}\n\treturn -1\n}',
)
text = text.replace(
    'func allowedChannel(channel string) bool {\n\treturn channel == "ACH" || channel == "CARD" || channel == "WIRE"\n}',
    'func clean(value string) string {\n\treturn strings.TrimSpace(value)\n}\n\nfunc allowedChannel(channel string) bool {\n\tchannel = strings.ToUpper(clean(channel))\n\treturn channel == "ACH" || channel == "CARD" || channel == "WIRE"\n}',
)
path.write_text(text)
PY

/app/scripts/run_batch.sh
test -s /app/out/reimbursement_report.csv
test -s /app/out/reimbursement_summary.json
