#!/usr/bin/env bash
set -euo pipefail

cd /app

if grep -q 'func loadOpenDates' /app/cmd/reconcile/main.go; then
  /app/scripts/run_batch.sh
  test -s /app/out/credit_report.csv
  test -s /app/out/credit_summary.json
  exit 0
fi

if ! grep -q 'func canonicalChannel' /app/cmd/reconcile/main.go; then
  if ! grep -q 'usedServices' /app/cmd/reconcile/main.go; then
python3 <<'PY'
from pathlib import Path

path = Path("/app/cmd/reconcile/main.go")
text = path.read_text()
text = text.replace('"strconv"', '"strconv"\n\t"strings"')
text = text.replace('amount, err := strconv.Atoi(row[2])', 'amount, err := strconv.Atoi(clean(row[2]))')
text = text.replace(
    'out = append(out, Service{ID: row[0], Customer: row[1], Amount: amount, Status: row[3], Channel: row[4]})',
    'out = append(out, Service{ID: clean(row[0]), Customer: clean(row[1]), Amount: amount, Status: strings.ToUpper(clean(row[3])), Channel: strings.ToUpper(clean(row[4]))})',
)
text = text.replace(
    'out = append(out, Credit{ServiceID: row[0], Customer: row[1], Amount: amount, Channel: row[3]})',
    'out = append(out, Credit{ServiceID: clean(row[0]), Customer: clean(row[1]), Amount: amount, Channel: strings.ToUpper(clean(row[3]))})',
)
text = text.replace(
    'summary.MatchedAmountCents -= credit.Amount',
    'summary.MatchedAmountCents += credit.Amount',
)
text = text.replace(
    'if len(service.ID) >= 8 && len(credit.ServiceID) >= 8 &&\n\t\t\tservice.ID[:8] == credit.ServiceID[:8] &&',
    'if service.ID == credit.ServiceID &&',
)
text = text.replace(
    'return channel == "ACH" || channel == "WIRE"',
    'return channel == "ACH" || channel == "CARD" || channel == "WIRE"',
)
text = text.replace(
    '\tsummary := Summary{}\n\tfor _, credit := range credits {\n\t\tmatch := findMatch(services, credit)',
    '\tsummary := Summary{}\n\tusedServices := make([]bool, len(services))\n\tfor _, credit := range credits {\n\t\tmatchIndex := findMatch(services, credit, usedServices)\n\t\tvar match *Service\n\t\tif matchIndex >= 0 {\n\t\t\tmatch = &services[matchIndex]\n\t\t\tusedServices[matchIndex] = true\n\t\t}',
)
text = text.replace(
    'func findMatch(services []Service, credit Credit) *Service {\n\tfor i := range services {\n\t\tservice := &services[i]\n\t\tif service.ID == credit.ServiceID &&',
    'func findMatch(services []Service, credit Credit, used []bool) int {\n\tfor i := range services {\n\t\tif used[i] {\n\t\t\tcontinue\n\t\t}\n\t\tservice := &services[i]\n\t\tif service.ID == credit.ServiceID &&',
)
text = text.replace(
    '\t\t\treturn service\n\t\t}\n\t}\n\treturn nil\n}',
    '\t\t\treturn i\n\t\t}\n\t}\n\treturn -1\n}',
)
text = text.replace(
    'func allowedChannel(channel string) bool {\n\treturn channel == "ACH" || channel == "CARD" || channel == "WIRE"\n}',
    'func clean(value string) string {\n\treturn strings.TrimSpace(value)\n}\n\nfunc allowedChannel(channel string) bool {\n\tchannel = strings.ToUpper(clean(channel))\n\treturn channel == "ACH" || channel == "CARD" || channel == "WIRE"\n}',
)
text = text.replace(
    'channel = match.Channel',
    'channel = credit.Channel',
)
path.write_text(text)
PY
  fi

python3 <<'PY'
from pathlib import Path

path = Path("/app/cmd/reconcile/main.go")
text = path.read_text()

text = text.replace(
    "Channel: strings.ToUpper(clean(row[4]))",
    "Channel: canonicalChannel(row[4])",
)
text = text.replace(
    "Channel: strings.ToUpper(clean(row[3]))",
    "Channel: canonicalChannel(row[3])",
)
text = text.replace(
    'func clean(value string) string {\n\treturn strings.TrimSpace(value)\n}\n\nfunc allowedChannel(channel string) bool {\n\tchannel = strings.ToUpper(clean(channel))\n\treturn channel == "ACH" || channel == "CARD" || channel == "WIRE"\n}',
    '''func clean(value string) string {
\treturn strings.TrimSpace(value)
}

func canonicalChannel(channel string) string {
\tswitch strings.ToUpper(clean(channel)) {
\tcase "CC":
\t\treturn "CARD"
\tcase "WIR":
\t\treturn "WIRE"
\tdefault:
\t\treturn strings.ToUpper(clean(channel))
\t}
}

func allowedChannel(channel string) bool {
\tchannel = canonicalChannel(channel)
\treturn channel == "ACH" || channel == "CARD" || channel == "WIRE"
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
    "type Service struct {\n\tID       string\n\tCustomer string\n\tAmount   int\n\tStatus   string\n\tChannel   string\n}",
    "type Service struct {\n\tID       string\n\tCustomer string\n\tAmount   int\n\tStatus   string\n\tChannel  string\n\tDueDate  string\n}",
)
text = text.replace(
    "type Credit struct {\n\tServiceID string\n\tCustomer  string\n\tAmount    int\n\tChannel    string\n}",
    "type Credit struct {\n\tServiceID     string\n\tCustomer   string\n\tAmount     int\n\tChannel    string\n\tCreditDate string\n}",
)
text = text.replace(
    "out = append(out, Service{ID: clean(row[0]), Customer: clean(row[1]), Amount: amount, Status: strings.ToUpper(clean(row[3])), Channel: canonicalChannel(row[4])})",
    '''dueDate := ""
\t\tif len(row) > 5 {
\t\t\tdueDate = clean(row[5])
\t\t}
\t\tout = append(out, Service{ID: clean(row[0]), Customer: clean(row[1]), Amount: amount, Status: strings.ToUpper(clean(row[3])), Channel: canonicalChannel(row[4]), DueDate: dueDate})''',
)
text = text.replace(
    "out = append(out, Credit{ServiceID: clean(row[0]), Customer: clean(row[1]), Amount: amount, Channel: canonicalChannel(row[3])})",
    '''creditDate := ""
\t\tif len(row) > 4 {
\t\t\tcreditDate = clean(row[4])
\t\t}
\t\tout = append(out, Credit{ServiceID: clean(row[0]), Customer: clean(row[1]), Amount: amount, Channel: canonicalChannel(row[3]), CreditDate: creditDate})''',
)
text = text.replace(
    "return writeOutputs(services, credits)",
    '''openDates, err := loadOpenDates("/app/config/cutoff_calendar.txt")
\tif err != nil {
\t\treturn err
\t}
\treturn writeOutputs(services, credits, openDates)''',
)
text = text.replace(
    "func writeOutputs(services []Service, credits []Credit) error {",
    "func writeOutputs(services []Service, credits []Credit, openDates map[string]bool) error {",
)
text = text.replace(
    "matchIndex := findMatch(services, credit, usedServices)",
    "matchIndex := findMatch(services, credit, usedServices, openDates)",
)
start = text.index("func findMatch(")
end = text.index("\nfunc clean(", start)
text = text[:start] + '''func findMatch(services []Service, credit Credit, used []bool, openDates map[string]bool) int {
\tbestIndex := -1
\tfor i := range services {
\t\tif used[i] {
\t\t\tcontinue
\t\t}
\t\tservice := &services[i]
\t\tif !openDates[credit.CreditDate] ||
\t\t\tcredit.CreditDate == "" ||
\t\t\tservice.DueDate == "" ||
\t\t\tcredit.CreditDate > service.DueDate ||
\t\t\tservice.ID != credit.ServiceID ||
\t\t\tservice.Customer != credit.Customer ||
\t\t\tservice.Amount != credit.Amount ||
\t\t\tservice.Status != "POSTED" ||
\t\t\t!allowedChannel(service.Channel) ||
\t\t\tservice.Channel != credit.Channel {
\t\t\tcontinue
\t\t}
\t\tif bestIndex < 0 ||
\t\t\tservice.DueDate > services[bestIndex].DueDate ||
\t\t\t(service.DueDate == services[bestIndex].DueDate && i < bestIndex) {
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
