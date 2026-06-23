#!/usr/bin/env bash
set -euo pipefail

cd /app

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

/app/scripts/run_batch.sh
test -s /app/out/rebate_report.csv
test -s /app/out/rebate_summary.json
