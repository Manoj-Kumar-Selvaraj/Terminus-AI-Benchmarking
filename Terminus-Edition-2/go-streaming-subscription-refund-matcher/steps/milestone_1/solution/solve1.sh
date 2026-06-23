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
    'out = append(out, Subscription{ID: row[0], Customer: row[1], Amount: amount, Status: row[3], Plan: row[4]})',
    'out = append(out, Subscription{ID: clean(row[0]), Customer: clean(row[1]), Amount: amount, Status: strings.ToUpper(clean(row[3])), Plan: strings.ToUpper(clean(row[4]))})',
)
text = text.replace(
    'out = append(out, Refund{SubscriptionID: row[0], Customer: row[1], Amount: amount, Plan: row[3]})',
    'out = append(out, Refund{SubscriptionID: clean(row[0]), Customer: clean(row[1]), Amount: amount, Plan: strings.ToUpper(clean(row[3]))})',
)
text = text.replace(
    'summary.MatchedAmountCents -= refund.Amount',
    'summary.MatchedAmountCents += refund.Amount',
)
text = text.replace(
    'if len(subscription.ID) >= 8 && len(refund.SubscriptionID) >= 8 &&\n\t\t\tsubscription.ID[:8] == refund.SubscriptionID[:8] &&',
    'if subscription.ID == refund.SubscriptionID &&',
)
text = text.replace(
    'return plan == "BASIC" || plan == "FAMILY" || plan == "PREMIUM"',
    'return plan == "BASIC" || plan == "FAMILY" || plan == "PREMIUM"',
)
text = text.replace(
    '\tsummary := Summary{}\n\tfor _, refund := range refunds {\n\t\tmatch := findMatch(subscriptions, refund)',
    '\tsummary := Summary{}\n\tusedSubscriptions := make([]bool, len(subscriptions))\n\tfor _, refund := range refunds {\n\t\tmatchIndex := findMatch(subscriptions, refund, usedSubscriptions)\n\t\tvar match *Subscription\n\t\tif matchIndex >= 0 {\n\t\t\tmatch = &subscriptions[matchIndex]\n\t\t\tusedSubscriptions[matchIndex] = true\n\t\t}',
)
text = text.replace(
    'func findMatch(subscriptions []Subscription, refund Refund) *Subscription {\n\tfor i := range subscriptions {\n\t\tsubscription := &subscriptions[i]\n\t\tif subscription.ID == refund.SubscriptionID &&',
    'func findMatch(subscriptions []Subscription, refund Refund, used []bool) int {\n\tfor i := range subscriptions {\n\t\tif used[i] {\n\t\t\tcontinue\n\t\t}\n\t\tsubscription := &subscriptions[i]\n\t\tif subscription.ID == refund.SubscriptionID &&',
)
text = text.replace(
    '\t\t\treturn subscription\n\t\t}\n\t}\n\treturn nil\n}',
    '\t\t\treturn i\n\t\t}\n\t}\n\treturn -1\n}',
)
text = text.replace(
    'func allowedPlan(plan string) bool {\n\treturn plan == "BASIC" || plan == "FAMILY" || plan == "PREMIUM"\n}',
    'func clean(value string) string {\n\treturn strings.TrimSpace(value)\n}\n\nfunc allowedPlan(plan string) bool {\n\tplan = strings.ToUpper(clean(plan))\n\treturn plan == "BASIC" || plan == "FAMILY" || plan == "PREMIUM"\n}',
)
path.write_text(text)
PY

/app/scripts/run_batch.sh
test -s /app/out/refund_report.csv
test -s /app/out/refund_summary.json
