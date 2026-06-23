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
    'out = append(out, Subscription{ID: row[0], Account: row[1], Amount: amount, Status: row[3], Channel: row[4]})',
    'out = append(out, Subscription{ID: clean(row[0]), Account: clean(row[1]), Amount: amount, Status: strings.ToUpper(clean(row[3])), Channel: strings.ToUpper(clean(row[4]))})',
)
text = text.replace(
    'out = append(out, Credit{SubscriptionID: row[0], Account: row[1], Amount: amount, Channel: row[3]})',
    'out = append(out, Credit{SubscriptionID: clean(row[0]), Account: clean(row[1]), Amount: amount, Channel: strings.ToUpper(clean(row[3]))})',
)
text = text.replace(
    'summary.MatchedAmountCents -= credit.Amount',
    'summary.MatchedAmountCents += credit.Amount',
)
text = text.replace(
    'if len(subscription.ID) >= 8 && len(credit.SubscriptionID) >= 8 &&\n\t\t\tsubscription.ID[:8] == credit.SubscriptionID[:8] &&',
    'if subscription.ID == credit.SubscriptionID &&',
)
text = text.replace(
    'return channel == "ACH" || channel == "WIRE"',
    'return channel == "ACH" || channel == "CARD" || channel == "WIRE"',
)
text = text.replace(
    '\tsummary := Summary{}\n\tfor _, credit := range credits {\n\t\tmatch := findMatch(subscriptions, credit)',
    '\tsummary := Summary{}\n\tusedSubscriptions := make([]bool, len(subscriptions))\n\tfor _, credit := range credits {\n\t\tmatchIndex := findMatch(subscriptions, credit, usedSubscriptions)\n\t\tvar match *Subscription\n\t\tif matchIndex >= 0 {\n\t\t\tmatch = &subscriptions[matchIndex]\n\t\t\tusedSubscriptions[matchIndex] = true\n\t\t}',
)
text = text.replace(
    'func findMatch(subscriptions []Subscription, credit Credit) *Subscription {\n\tfor i := range subscriptions {\n\t\tsubscription := &subscriptions[i]\n\t\tif subscription.ID == credit.SubscriptionID &&',
    'func findMatch(subscriptions []Subscription, credit Credit, used []bool) int {\n\tfor i := range subscriptions {\n\t\tif used[i] {\n\t\t\tcontinue\n\t\t}\n\t\tsubscription := &subscriptions[i]\n\t\tif subscription.ID == credit.SubscriptionID &&',
)
text = text.replace(
    '\t\t\treturn subscription\n\t\t}\n\t}\n\treturn nil\n}',
    '\t\t\treturn i\n\t\t}\n\t}\n\treturn -1\n}',
)
text = text.replace(
    'func allowedChannel(channel string) bool {\n\treturn channel == "ACH" || channel == "CARD" || channel == "WIRE"\n}',
    'func clean(value string) string {\n\treturn strings.TrimSpace(value)\n}\n\nfunc allowedChannel(channel string) bool {\n\tchannel = strings.ToUpper(clean(channel))\n\treturn channel == "ACH" || channel == "CARD" || channel == "WIRE"\n}',
)
path.write_text(text)
PY

/app/scripts/run_batch.sh
test -s /app/out/credit_report.csv
test -s /app/out/credit_summary.json
