#!/usr/bin/env bash
set -euo pipefail

cd /app

python3 <<'PY'
from pathlib import Path

path = Path("/app/cmd/reconcile/main.go")
text = path.read_text()

text = text.replace(
    "type Account struct {\n\tID       string\n\tCustomer string\n\tAmount   int\n\tStatus   string\n\tChannel   string\n}",
    "type Account struct {\n\tID       string\n\tCustomer string\n\tAmount   int\n\tStatus   string\n\tChannel  string\n\tDueDate  string\n}",
)
text = text.replace(
    "type Reimbursement struct {\n\tAccountID string\n\tCustomer  string\n\tAmount    int\n\tChannel    string\n}",
    "type Reimbursement struct {\n\tAccountID     string\n\tCustomer   string\n\tAmount     int\n\tChannel    string\n\tReimbursementDate string\n}",
)
text = text.replace(
    "out = append(out, Account{ID: clean(row[0]), Customer: clean(row[1]), Amount: amount, Status: strings.ToUpper(clean(row[3])), Channel: canonicalChannel(row[4])})",
    '''dueDate := ""
\t\tif len(row) > 5 {
\t\t\tdueDate = clean(row[5])
\t\t}
\t\tout = append(out, Account{ID: clean(row[0]), Customer: clean(row[1]), Amount: amount, Status: strings.ToUpper(clean(row[3])), Channel: canonicalChannel(row[4]), DueDate: dueDate})''',
)
text = text.replace(
    "out = append(out, Reimbursement{AccountID: clean(row[0]), Customer: clean(row[1]), Amount: amount, Channel: canonicalChannel(row[3])})",
    '''reimbursementDate := ""
\t\tif len(row) > 4 {
\t\t\treimbursementDate = clean(row[4])
\t\t}
\t\tout = append(out, Reimbursement{AccountID: clean(row[0]), Customer: clean(row[1]), Amount: amount, Channel: canonicalChannel(row[3]), ReimbursementDate: reimbursementDate})''',
)
text = text.replace(
    "return writeOutputs(accounts, reimbursements)",
    '''openDates, err := loadOpenDates("/app/config/cutoff_calendar.txt")
\tif err != nil {
\t\treturn err
\t}
\treturn writeOutputs(accounts, reimbursements, openDates)''',
)
text = text.replace(
    "func writeOutputs(accounts []Account, reimbursements []Reimbursement) error {",
    "func writeOutputs(accounts []Account, reimbursements []Reimbursement, openDates map[string]bool) error {",
)
text = text.replace(
    "matchIndex := findMatch(accounts, reimbursement, usedAccounts)",
    "matchIndex := findMatch(accounts, reimbursement, usedAccounts, openDates)",
)
start = text.index("func findMatch(")
end = text.index("\nfunc clean(", start)
text = text[:start] + '''func findMatch(accounts []Account, reimbursement Reimbursement, used []bool, openDates map[string]bool) int {
\tbestIndex := -1
\tfor i := range accounts {
\t\tif used[i] {
\t\t\tcontinue
\t\t}
\t\taccount := &accounts[i]
\t\tif !openDates[reimbursement.ReimbursementDate] ||
\t\t\treimbursement.ReimbursementDate == "" ||
\t\t\taccount.DueDate == "" ||
\t\t\treimbursement.ReimbursementDate > account.DueDate ||
\t\t\taccount.ID != reimbursement.AccountID ||
\t\t\taccount.Customer != reimbursement.Customer ||
\t\t\taccount.Amount != reimbursement.Amount ||
\t\t\taccount.Status != "POSTED" ||
\t\t\t!allowedChannel(account.Channel) ||
\t\t\taccount.Channel != reimbursement.Channel {
\t\t\tcontinue
\t\t}
\t\tif bestIndex < 0 || account.DueDate > accounts[bestIndex].DueDate {
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
test -s /app/out/reimbursement_report.csv
test -s /app/out/reimbursement_summary.json
