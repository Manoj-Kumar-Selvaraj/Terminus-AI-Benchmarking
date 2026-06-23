#!/usr/bin/env bash
set -euo pipefail

cd /app

python3 <<'PY'
from pathlib import Path

path = Path("/app/cmd/reconcile/main.go")
text = path.read_text()

text = text.replace(
    "type Subscription struct {\n\tID       string\n\tCustomer string\n\tAmount   int\n\tStatus   string\n\tPlan   string\n}",
    "type Subscription struct {\n\tID       string\n\tCustomer string\n\tAmount   int\n\tStatus   string\n\tPlan  string\n\tCycleEnd  string\n}",
)
text = text.replace(
    "type Refund struct {\n\tSubscriptionID string\n\tCustomer  string\n\tAmount    int\n\tPlan    string\n}",
    "type Refund struct {\n\tSubscriptionID     string\n\tCustomer   string\n\tAmount     int\n\tPlan    string\n\tRefundDate string\n}",
)
text = text.replace(
    "out = append(out, Subscription{ID: clean(row[0]), Customer: clean(row[1]), Amount: amount, Status: strings.ToUpper(clean(row[3])), Plan: canonicalPlan(row[4])})",
    '''dueDate := ""
\t\tif len(row) > 5 {
\t\t\tdueDate = clean(row[5])
\t\t}
\t\tout = append(out, Subscription{ID: clean(row[0]), Customer: clean(row[1]), Amount: amount, Status: strings.ToUpper(clean(row[3])), Plan: canonicalPlan(row[4]), CycleEnd: dueDate})''',
)
text = text.replace(
    "out = append(out, Refund{SubscriptionID: clean(row[0]), Customer: clean(row[1]), Amount: amount, Plan: canonicalPlan(row[3])})",
    '''refundDate := ""
\t\tif len(row) > 4 {
\t\t\trefundDate = clean(row[4])
\t\t}
\t\tout = append(out, Refund{SubscriptionID: clean(row[0]), Customer: clean(row[1]), Amount: amount, Plan: canonicalPlan(row[3]), RefundDate: refundDate})''',
)
text = text.replace(
    "return writeOutputs(subscriptions, refunds)",
    '''openDates, err := loadOpenDates("/app/config/cutoff_calendar.txt")
\tif err != nil {
\t\treturn err
\t}
\treturn writeOutputs(subscriptions, refunds, openDates)''',
)
text = text.replace(
    "func writeOutputs(subscriptions []Subscription, refunds []Refund) error {",
    "func writeOutputs(subscriptions []Subscription, refunds []Refund, openDates map[string]bool) error {",
)
text = text.replace(
    "matchIndex := findMatch(subscriptions, refund, usedSubscriptions)",
    "matchIndex := findMatch(subscriptions, refund, usedSubscriptions, openDates)",
)
start = text.index("func findMatch(")
end = text.index("\nfunc clean(", start)
text = text[:start] + '''func findMatch(subscriptions []Subscription, refund Refund, used []bool, openDates map[string]bool) int {
\tbestIndex := -1
\tfor i := range subscriptions {
\t\tif used[i] {
\t\t\tcontinue
\t\t}
\t\tsubscription := &subscriptions[i]
\t\tif !openDates[refund.RefundDate] ||
\t\t\trefund.RefundDate == "" ||
\t\t\tsubscription.CycleEnd == "" ||
\t\t\trefund.RefundDate > subscription.CycleEnd ||
\t\t\tsubscription.ID != refund.SubscriptionID ||
\t\t\tsubscription.Customer != refund.Customer ||
\t\t\tsubscription.Amount != refund.Amount ||
\t\t\tsubscription.Status != "ACTIVE" ||
\t\t\t!allowedPlan(subscription.Plan) ||
\t\t\tsubscription.Plan != refund.Plan {
\t\t\tcontinue
\t\t}
\t\tif bestIndex < 0 || subscription.CycleEnd > subscriptions[bestIndex].CycleEnd {
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
test -s /app/out/refund_report.csv
test -s /app/out/refund_summary.json
