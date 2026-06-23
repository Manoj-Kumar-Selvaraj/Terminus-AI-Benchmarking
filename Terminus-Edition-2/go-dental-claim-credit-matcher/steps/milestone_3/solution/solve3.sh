#!/usr/bin/env bash
set -euo pipefail

cd /app

python3 <<'PY'
from pathlib import Path

path = Path("/app/cmd/reconcile/main.go")
text = path.read_text()
if "func loadOpenDates(path string)" in text:
    raise SystemExit(0)
if '"strings"' not in text:
    text = text.replace('"strconv"', '"strconv"\n\t"strings"')

text = text.replace(
    "type Claim struct {\n\tID       string\n\tPatient string\n\tAmount   int\n\tStatus   string\n\tProcedure   string\n}",
    "type Claim struct {\n\tID       string\n\tPatient string\n\tAmount   int\n\tStatus   string\n\tProcedure  string\n\tServiceDate  string\n}",
)
text = text.replace(
    "type Credit struct {\n\tClaimID string\n\tPatient  string\n\tAmount    int\n\tProcedure    string\n}",
    "type Credit struct {\n\tClaimID     string\n\tPatient   string\n\tAmount     int\n\tProcedure    string\n\tCreditDate string\n}",
)
text = text.replace(
    "out = append(out, Claim{ID: clean(row[0]), Patient: clean(row[1]), Amount: amount, Status: strings.ToUpper(clean(row[3])), Procedure: canonicalProcedure(row[4])})",
    '''serviceDate := ""
\t\tif len(row) > 5 {
\t\t\tserviceDate = clean(row[5])
\t\t}
\t\tout = append(out, Claim{ID: clean(row[0]), Patient: clean(row[1]), Amount: amount, Status: strings.ToUpper(clean(row[3])), Procedure: canonicalProcedure(row[4]), ServiceDate: serviceDate})''',
)
text = text.replace(
    "out = append(out, Credit{ClaimID: clean(row[0]), Patient: clean(row[1]), Amount: amount, Procedure: canonicalProcedure(row[3])})",
    '''creditDate := ""
\t\tif len(row) > 4 {
\t\t\tcreditDate = clean(row[4])
\t\t}
\t\tout = append(out, Credit{ClaimID: clean(row[0]), Patient: clean(row[1]), Amount: amount, Procedure: canonicalProcedure(row[3]), CreditDate: creditDate})''',
)
text = text.replace(
    "return writeOutputs(claims, credits)",
    '''openDates, err := loadOpenDates("/app/config/cutoff_calendar.txt")
\tif err != nil {
\t\treturn err
\t}
\treturn writeOutputs(claims, credits, openDates)''',
)
text = text.replace(
    "func writeOutputs(claims []Claim, credits []Credit) error {",
    "func writeOutputs(claims []Claim, credits []Credit, openDates map[string]bool) error {",
)
text = text.replace(
    "matchIndex := findMatch(claims, credit, usedClaims)",
    "matchIndex := findMatch(claims, credit, usedClaims, openDates)",
)
start = text.index("func findMatch(")
end = text.index("\nfunc clean(", start)
text = text[:start] + '''func findMatch(claims []Claim, credit Credit, used []bool, openDates map[string]bool) int {
\tbestIndex := -1
\tfor i := range claims {
\t\tif used[i] {
\t\t\tcontinue
\t\t}
\t\tclaim := &claims[i]
\t\tif !validDate(credit.CreditDate) ||
\t\t\t!validDate(claim.ServiceDate) ||
\t\t\t!openDates[credit.CreditDate] ||
\t\t\tcredit.CreditDate == "" ||
\t\t\tclaim.ServiceDate == "" ||
\t\t\tcredit.CreditDate > claim.ServiceDate ||
\t\t\tclaim.ID != credit.ClaimID ||
\t\t\tclaim.Patient != credit.Patient ||
\t\t\tclaim.Amount != credit.Amount ||
\t\t\tclaim.Status != "APPROVED" ||
\t\t\t!allowedProcedure(claim.Procedure) ||
\t\t\tclaim.Procedure != credit.Procedure {
\t\t\tcontinue
\t\t}
\t\tif bestIndex < 0 || claim.ServiceDate > claims[bestIndex].ServiceDate {
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
\t\tif len(fields) >= 2 && validDate(fields[0]) && strings.EqualFold(fields[1], "open") {
\t\t\topenDates[fields[0]] = true
\t\t}
\t}
\treturn openDates, nil
}

func validDate(value string) bool {
\tif len(value) != 10 || value[4] != '-' || value[7] != '-' {
\t\treturn false
\t}
\tfor i, r := range value {
\t\tif i == 4 || i == 7 {
\t\t\tcontinue
\t\t}
\t\tif r < '0' || r > '9' {
\t\t\treturn false
\t\t}
\t}
\tmonth := value[5:7]
\tday := value[8:10]
\treturn month >= "01" && month <= "12" && day >= "01" && day <= "31"
}
''' + text[end:]

path.write_text(text)
PY

/app/scripts/run_batch.sh
test -s /app/out/credit_report.csv
test -s /app/out/credit_summary.json
