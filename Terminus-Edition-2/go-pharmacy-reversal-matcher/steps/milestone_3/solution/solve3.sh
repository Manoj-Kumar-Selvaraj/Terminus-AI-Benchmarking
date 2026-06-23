#!/usr/bin/env bash
set -euo pipefail

cd /app

python3 <<'PY'
from pathlib import Path

path = Path("/app/cmd/reconcile/main.go")
text = path.read_text()

text = text.replace(
    "type Fill struct {\n\tID       string\n\tMember string\n\tAmount   int\n\tStatus   string\n\tReason   string\n}",
    "type Fill struct {\n\tID          string\n\tMember      string\n\tAmount      int\n\tStatus      string\n\tReason      string\n\tServiceDate string\n}",
)
text = text.replace(
    "type Reversal struct {\n\tFillID string\n\tMember  string\n\tAmount    int\n\tReason    string\n}",
    "type Reversal struct {\n\tFillID       string\n\tMember       string\n\tAmount       int\n\tReason       string\n\tReversalDate string\n}",
)
text = text.replace(
    "out = append(out, Fill{ID: clean(row[0]), Member: clean(row[1]), Amount: amount, Status: strings.ToUpper(clean(row[3])), Reason: canonicalReason(row[4])})",
    '''serviceDate := ""
\t\tif len(row) > 5 {
\t\t\tserviceDate = clean(row[5])
\t\t}
\t\tout = append(out, Fill{ID: clean(row[0]), Member: clean(row[1]), Amount: amount, Status: strings.ToUpper(clean(row[3])), Reason: canonicalReason(row[4]), ServiceDate: serviceDate})''',
)
text = text.replace(
    "out = append(out, Reversal{FillID: clean(row[0]), Member: clean(row[1]), Amount: amount, Reason: canonicalReason(row[3])})",
    '''reversalDate := ""
\t\tif len(row) > 4 {
\t\t\treversalDate = clean(row[4])
\t\t}
\t\tout = append(out, Reversal{FillID: clean(row[0]), Member: clean(row[1]), Amount: amount, Reason: canonicalReason(row[3]), ReversalDate: reversalDate})''',
)
text = text.replace(
    "return writeOutputs(fills, reversals)",
    '''openDates, err := loadOpenDates("/app/config/cutoff_calendar.txt")
\tif err != nil {
\t\treturn err
\t}
\treturn writeOutputs(fills, reversals, openDates)''',
)
text = text.replace(
    "func writeOutputs(fills []Fill, reversals []Reversal) error {",
    "func writeOutputs(fills []Fill, reversals []Reversal, openDates map[string]bool) error {",
)
text = text.replace(
    "matchIndex := findMatch(fills, reversal, usedFills)",
    "matchIndex := findMatch(fills, reversal, usedFills, openDates)",
)
start = text.index("func findMatch(")
end = text.index("\nfunc clean(", start)
text = text[:start] + '''func findMatch(fills []Fill, reversal Reversal, used []bool, openDates map[string]bool) int {
\tbestIndex := -1
\tfor i := range fills {
\t\tif used[i] {
\t\t\tcontinue
\t\t}
\t\tfill := &fills[i]
\t\tif !openDates[reversal.ReversalDate] ||
\t\t\treversal.ReversalDate == "" ||
\t\t\tfill.ServiceDate == "" ||
\t\t\tfill.ServiceDate > reversal.ReversalDate ||
\t\t\tfill.ID != reversal.FillID ||
\t\t\tfill.Member != reversal.Member ||
\t\t\tfill.Amount != reversal.Amount ||
\t\t\tfill.Status != "POSTED" ||
\t\t\t!allowedReason(fill.Reason) ||
\t\t\tfill.Reason != reversal.Reason {
\t\t\tcontinue
\t\t}
\t\tif bestIndex < 0 || fill.ServiceDate > fills[bestIndex].ServiceDate {
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
test -s /app/out/reversal_report.csv
test -s /app/out/reversal_summary.json
