#!/usr/bin/env bash
set -euo pipefail

cd /app

if grep -q 'func detectDatedMode' /app/cmd/reconcile/main.go; then
  /app/scripts/run_batch.sh
  test -s /app/out/rebate_report.csv
  test -s /app/out/rebate_summary.json
  exit 0
fi

if ! grep -q 'usedSponsorships' /app/cmd/reconcile/main.go; then
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
fi

if ! grep -q 'func canonicalLevel' /app/cmd/reconcile/main.go; then
python3 <<'PY'
from pathlib import Path

path = Path("/app/cmd/reconcile/main.go")
text = path.read_text()

text = text.replace(
    "Level: strings.ToUpper(clean(row[4]))",
    "Level: canonicalLevel(row[4])",
)
text = text.replace(
    "Level: strings.ToUpper(clean(row[3]))",
    "Level: canonicalLevel(row[3])",
)
text = text.replace(
    'func clean(value string) string {\n\treturn strings.TrimSpace(value)\n}\n\nfunc allowedLevel(level string) bool {\n\tlevel = strings.ToUpper(clean(level))\n\treturn level == "BRONZE" || level == "GOLD" || level == "PLATINUM"\n}',
    '''func clean(value string) string {
\treturn strings.TrimSpace(value)
}

func canonicalLevel(level string) string {
\tswitch strings.ToUpper(clean(level)) {
\tcase "BRZ":
\t\treturn "BRONZE"
\tcase "GLD":
\t\treturn "GOLD"
\tcase "PLT":
\t\treturn "PLATINUM"
\tdefault:
\t\treturn strings.ToUpper(clean(level))
\t}
}

func allowedLevel(level string) bool {
\tlevel = canonicalLevel(level)
\treturn level == "BRONZE" || level == "GOLD" || level == "PLATINUM"
}''',
)

path.write_text(text)
PY
fi

python3 <<'PY'
from pathlib import Path

path = Path("/app/cmd/reconcile/main.go")
text = path.read_text()

text = text.replace(
    "type Sponsorship struct {\n\tID       string\n\tCustomer string\n\tAmount   int\n\tStatus   string\n\tLevel   string\n}",
    "type Sponsorship struct {\n\tID        string\n\tCustomer  string\n\tAmount    int\n\tStatus    string\n\tLevel     string\n\tEventEnd  string\n}",
)
text = text.replace(
    "type Rebate struct {\n\tSponsorshipID string\n\tCustomer  string\n\tAmount    int\n\tLevel    string\n}",
    "type Rebate struct {\n\tSponsorshipID string\n\tCustomer      string\n\tAmount        int\n\tLevel         string\n\tRebateDate    string\n}",
)
text = text.replace(
    "out = append(out, Sponsorship{ID: clean(row[0]), Customer: clean(row[1]), Amount: amount, Status: strings.ToUpper(clean(row[3])), Level: canonicalLevel(row[4])})",
    '''eventEnd := ""
\t\tif len(row) > 5 {
\t\t\teventEnd = clean(row[5])
\t\t}
\t\tout = append(out, Sponsorship{ID: clean(row[0]), Customer: clean(row[1]), Amount: amount, Status: strings.ToUpper(clean(row[3])), Level: canonicalLevel(row[4]), EventEnd: eventEnd})''',
)
text = text.replace(
    "out = append(out, Rebate{SponsorshipID: clean(row[0]), Customer: clean(row[1]), Amount: amount, Level: canonicalLevel(row[3])})",
    '''rebateDate := ""
\t\tif len(row) > 4 {
\t\t\trebateDate = clean(row[4])
\t\t}
\t\tout = append(out, Rebate{SponsorshipID: clean(row[0]), Customer: clean(row[1]), Amount: amount, Level: canonicalLevel(row[3]), RebateDate: rebateDate})''',
)
text = text.replace(
    "return writeOutputs(sponsorships, rebates)",
    '''datedMode, err := detectDatedMode()
\tif err != nil {
\t\treturn err
\t}
\topenDates := map[string]bool{}
\tif datedMode {
\t\topenDates, err = loadOpenDates("/app/config/cutoff_calendar.txt")
\t\tif err != nil {
\t\t\treturn err
\t\t}
\t}
\treturn writeOutputs(sponsorships, rebates, openDates, datedMode)''',
)
text = text.replace(
    "func writeOutputs(sponsorships []Sponsorship, rebates []Rebate) error {",
    "func writeOutputs(sponsorships []Sponsorship, rebates []Rebate, openDates map[string]bool, datedMode bool) error {",
)
text = text.replace(
    "matchIndex := findMatch(sponsorships, rebate, usedSponsorships)",
    "matchIndex := findMatch(sponsorships, rebate, usedSponsorships, openDates, datedMode)",
)
start = text.index("func findMatch(")
end = text.index("\nfunc clean(", start)
text = text[:start] + '''func findMatch(sponsorships []Sponsorship, rebate Rebate, used []bool, openDates map[string]bool, datedMode bool) int {
\tbestIndex := -1
\tfor i := range sponsorships {
\t\tif used[i] {
\t\t\tcontinue
\t\t}
\t\tsponsorship := &sponsorships[i]
\t\tif datedMode {
\t\t\tif !openDates[rebate.RebateDate] ||
\t\t\t\trebate.RebateDate == "" ||
\t\t\t\tsponsorship.EventEnd == "" ||
\t\t\t\trebate.RebateDate > sponsorship.EventEnd {
\t\t\t\tcontinue
\t\t\t}
\t\t}
\t\tif sponsorship.ID != rebate.SponsorshipID ||
\t\t\tsponsorship.Customer != rebate.Customer ||
\t\t\tsponsorship.Amount != rebate.Amount ||
\t\t\tsponsorship.Status != "SIGNED" ||
\t\t\t!allowedLevel(sponsorship.Level) ||
\t\t\tsponsorship.Level != rebate.Level {
\t\t\tcontinue
\t\t}
\t\tif !datedMode {
\t\t\treturn i
\t\t}
\t\tif bestIndex < 0 || sponsorship.EventEnd > sponsorships[bestIndex].EventEnd {
\t\t\tbestIndex = i
\t\t} else if sponsorship.EventEnd == sponsorships[bestIndex].EventEnd && i < bestIndex {
\t\t\tbestIndex = i
\t\t}
\t}
\treturn bestIndex
}

func detectDatedMode() (bool, error) {
\tbookingHeader, err := readHeader("/app/data/sponsorships.csv")
\tif err != nil {
\t\treturn false, err
\t}
\trefundHeader, err := readHeader("/app/data/rebates.csv")
\tif err != nil {
\t\treturn false, err
\t}
\treturn contains(bookingHeader, "event_end") && contains(refundHeader, "rebate_date"), nil
}

func readHeader(path string) ([]string, error) {
\tf, err := os.Open(path)
\tif err != nil {
\t\treturn nil, err
\t}
\tdefer f.Close()
\treader := csv.NewReader(f)
\treader.FieldsPerRecord = -1
\treturn reader.Read()
}

func contains(values []string, target string) bool {
\tfor _, value := range values {
\t\tif strings.EqualFold(strings.TrimSpace(value), target) {
\t\t\treturn true
\t\t}
\t}
\treturn false
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
test -s /app/out/rebate_report.csv
test -s /app/out/rebate_summary.json
