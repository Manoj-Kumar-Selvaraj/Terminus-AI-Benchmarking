#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

cd /app

if grep -q 'func canonicalChannel' /app/cmd/reconcile/main.go; then
  /app/scripts/run_batch.sh
  test -s /app/out/credit_report.csv
  test -s /app/out/credit_summary.json
  exit 0
fi

if ! grep -q 'usedVisits' /app/cmd/reconcile/main.go; then
  bash "$SCRIPT_DIR/solve1.sh"
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

/app/scripts/run_batch.sh
test -s /app/out/credit_report.csv
test -s /app/out/credit_summary.json
