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
path.write_text(text)
PY

/app/scripts/run_batch.sh
test -s /app/out/credit_report.csv
test -s /app/out/credit_summary.json
