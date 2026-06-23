#!/usr/bin/env bash
set -euo pipefail

cd /app

python3 <<'PY'
from pathlib import Path

path = Path("/app/cmd/reconcile/main.go")
text = path.read_text()

text = text.replace(
    'import (\n\t"encoding/csv"\n\t"encoding/json"\n\t"fmt"\n\t"os"\n\t"path/filepath"\n\t"strconv"\n\t"strings"\n)',
    'import (\n\t"encoding/csv"\n\t"encoding/json"\n\t"fmt"\n\t"os"\n\t"path/filepath"\n\t"strconv"\n\t"strings"\n)',
)
text = text.replace(
    "type Subscription struct {\n\tID       string\n\tAccount string\n\tAmount   int\n\tStatus   string\n\tChannel   string\n}",
    "type Subscription struct {\n\tID       string\n\tAccount string\n\tAmount   int\n\tStatus   string\n\tChannel   string\n\tDueDate  string\n}",
)
text = text.replace(
    "type Credit struct {\n\tSubscriptionID string\n\tAccount  string\n\tAmount    int\n\tChannel    string\n}",
    "type Credit struct {\n\tSubscriptionID    string\n\tAccount     string\n\tAmount       int\n\tChannel       string\n\tCreditDate  string\n}",
)
text = text.replace(
    "out = append(out, Subscription{ID: clean(row[0]), Account: clean(row[1]), Amount: amount, Status: strings.ToUpper(clean(row[3])), Channel: canonicalChannel(row[4])})",
    '''dueDate := ""
\t\tif len(row) > 5 {
\t\t\tdueDate = clean(row[5])
\t\t}
\t\tout = append(out, Subscription{ID: clean(row[0]), Account: clean(row[1]), Amount: amount, Status: strings.ToUpper(clean(row[3])), Channel: canonicalChannel(row[4]), DueDate: dueDate})''',
)
text = text.replace(
    "out = append(out, Credit{SubscriptionID: clean(row[0]), Account: clean(row[1]), Amount: amount, Channel: canonicalChannel(row[3])})",
    '''creditDate := ""
\t\tif len(row) > 4 {
\t\t\tcreditDate = clean(row[4])
\t\t}
\t\tout = append(out, Credit{SubscriptionID: clean(row[0]), Account: clean(row[1]), Amount: amount, Channel: canonicalChannel(row[3]), CreditDate: creditDate})''',
)
text = text.replace(
    "return writeOutputs(subscriptions, credits)",
    '''openDates, err := loadOpenDates("/app/config/cutoff_calendar.txt")
\tif err != nil {
\t\treturn err
\t}
\treturn writeOutputs(subscriptions, credits, openDates)''',
)
text = text.replace(
    "func writeOutputs(subscriptions []Subscription, credits []Credit) error {",
    "func writeOutputs(subscriptions []Subscription, credits []Credit, openDates map[string]bool) error {",
)
text = text.replace(
    "matchIndex := findMatch(subscriptions, credit, usedSubscriptions)",
    "matchIndex := findMatch(subscriptions, credit, usedSubscriptions, openDates)",
)
start = text.index("func findMatch(")
end = text.index("\nfunc clean(", start)
text = text[:start] + '''func findMatch(subscriptions []Subscription, credit Credit, used []bool, openDates map[string]bool) int {
\tbestIndex := -1
\tfor i := range subscriptions {
\t\tsubscription := &subscriptions[i]
\t\tif used[i] ||
\t\t\t!openDates[credit.CreditDate] ||
\t\t\tcredit.CreditDate == "" ||
\t\t\tsubscription.DueDate == "" ||
\t\t\tcredit.CreditDate > subscription.DueDate ||
\t\t\tsubscription.ID != credit.SubscriptionID ||
\t\t\tsubscription.Account != credit.Account ||
\t\t\tsubscription.Amount != credit.Amount ||
\t\t\tsubscription.Status != "POSTED" ||
\t\t\t!allowedChannel(subscription.Channel) ||
\t\t\tsubscription.Channel != credit.Channel {
\t\t\tcontinue
\t\t}
\t\tif bestIndex < 0 || subscription.DueDate > subscriptions[bestIndex].DueDate {
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
