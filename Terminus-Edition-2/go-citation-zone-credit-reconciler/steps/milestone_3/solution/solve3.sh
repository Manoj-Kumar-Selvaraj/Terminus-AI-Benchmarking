#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ -f "$SCRIPT_DIR/solve2.sh" ]; then
  bash "$SCRIPT_DIR/solve2.sh"
fi

cd /app

python3 <<'PY'
from pathlib import Path

path = Path("/app/cmd/reconcile/main.go")
text = path.read_text()

text = text.replace(
    "type Citation struct {\n\tID       string\n\tCustomer string\n\tAmount   int\n\tStatus   string\n\tZone   string\n}",
    "type Citation struct {\n\tID       string\n\tCustomer string\n\tAmount   int\n\tStatus   string\n\tZone  string\n\tDueDate  string\n}",
)
text = text.replace(
    "type Credit struct {\n\tCitationID string\n\tCustomer  string\n\tAmount    int\n\tZone    string\n}",
    "type Credit struct {\n\tCitationID     string\n\tCustomer   string\n\tAmount     int\n\tZone    string\n\tCreditDate string\n}",
)
text = text.replace(
    "out = append(out, Citation{ID: clean(row[0]), Customer: clean(row[1]), Amount: amount, Status: strings.ToUpper(clean(row[3])), Zone: canonicalZone(row[4])})",
    '''dueDate := ""
\t\tif len(row) > 5 {
\t\t\tdueDate = clean(row[5])
\t\t}
\t\tout = append(out, Citation{ID: clean(row[0]), Customer: clean(row[1]), Amount: amount, Status: strings.ToUpper(clean(row[3])), Zone: canonicalZone(row[4]), DueDate: dueDate})''',
)
text = text.replace(
    "out = append(out, Credit{CitationID: clean(row[0]), Customer: clean(row[1]), Amount: amount, Zone: canonicalZone(row[3])})",
    '''creditDate := ""
\t\tif len(row) > 4 {
\t\t\tcreditDate = clean(row[4])
\t\t}
\t\tout = append(out, Credit{CitationID: clean(row[0]), Customer: clean(row[1]), Amount: amount, Zone: canonicalZone(row[3]), CreditDate: creditDate})''',
)
text = text.replace(
    "return writeOutputs(citations, credits)",
    '''openDates, err := loadOpenDates("/app/config/cutoff_calendar.txt")
\tif err != nil {
\t\treturn err
\t}
\treturn writeOutputs(citations, credits, openDates)''',
)
text = text.replace(
    "func writeOutputs(citations []Citation, credits []Credit) error {",
    "func writeOutputs(citations []Citation, credits []Credit, openDates map[string]bool) error {",
)
text = text.replace(
    "matchIndex := findMatch(citations, credit, usedCitations)",
    "matchIndex := findMatch(citations, credit, usedCitations, openDates)",
)
start = text.index("func findMatch(")
end = text.index("\nfunc clean(", start)
text = text[:start] + '''func findMatch(citations []Citation, credit Credit, used []bool, openDates map[string]bool) int {
\tbestIndex := -1
\tfor i := range citations {
\t\tif used[i] {
\t\t\tcontinue
\t\t}
\t\tcitation := &citations[i]
\t\tif !openDates[credit.CreditDate] ||
\t\t\tcredit.CreditDate == "" ||
\t\t\tcitation.DueDate == "" ||
\t\t\tcredit.CreditDate > citation.DueDate ||
\t\t\tcitation.ID != credit.CitationID ||
\t\t\tcitation.Customer != credit.Customer ||
\t\t\tcitation.Amount != credit.Amount ||
\t\t\tcitation.Status != "PAID" ||
\t\t\t!allowedZone(citation.Zone) ||
\t\t\tcitation.Zone != credit.Zone {
\t\t\tcontinue
\t\t}
\t\tif bestIndex < 0 || citation.DueDate > citations[bestIndex].DueDate {
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
test -s /app/out/credit_report.csv
test -s /app/out/credit_summary.json
