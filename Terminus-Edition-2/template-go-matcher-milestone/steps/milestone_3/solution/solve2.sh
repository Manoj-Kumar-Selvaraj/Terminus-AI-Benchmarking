#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd /app

if ! grep -q 'func canonicalTier' /app/cmd/reconcile/main.go; then
  if ! grep -q 'usedRecords' /app/cmd/reconcile/main.go; then
    bash "$SCRIPT_DIR/solve1.sh"
  fi
fi

if grep -q 'func canonicalTier' /app/cmd/reconcile/main.go; then
  /app/scripts/run_batch.sh
  test -s /app/out/template_report.csv
  test -s /app/out/template_summary.json
  exit 0
fi

python3 <<'PY'
from pathlib import Path

path = Path("/app/cmd/reconcile/main.go")
text = path.read_text()

text = text.replace(
    "Tier: strings.ToUpper(clean(row[4]))",
    "Tier: canonicalTier(row[4])",
)
text = text.replace(
    "Tier: strings.ToUpper(clean(row[3]))",
    "Tier: canonicalTier(row[3])",
)
text = text.replace(
    'func clean(value string) string {\n\treturn strings.TrimSpace(value)\n}\n\nfunc allowedTier(tier string) bool {\n\ttier = strings.ToUpper(clean(tier))\n\treturn tier == "TIER_A" || tier == "TIER_B"\n}',
    '''func clean(value string) string {
\treturn strings.TrimSpace(value)
}

func canonicalTier(tier string) string {
\tswitch strings.ToUpper(clean(tier)) {
\tcase "TA":
\t\treturn "TIER_A"
\tcase "TB":
\t\treturn "TIER_B"
\tdefault:
\t\treturn strings.ToUpper(clean(tier))
\t}
}

func allowedTier(tier string) bool {
\ttier = canonicalTier(tier)
\treturn tier == "TIER_A" || tier == "TIER_B"
}''',
)

path.write_text(text)
PY

/app/scripts/run_batch.sh
test -s /app/out/template_report.csv
test -s /app/out/template_summary.json
