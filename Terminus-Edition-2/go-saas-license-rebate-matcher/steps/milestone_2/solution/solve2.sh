#!/usr/bin/env bash
set -euo pipefail

cd /app

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
    'func clean(value string) string {\n\treturn strings.TrimSpace(value)\n}\n\nfunc allowedTier(tier string) bool {\n\ttier = strings.ToUpper(clean(tier))\n\treturn tier == "STARTER" || tier == "BUSINESS" || tier == "ENTERPRISE"\n}',
    '''func clean(value string) string {
\treturn strings.TrimSpace(value)
}

func canonicalTier(tier string) string {
	switch strings.ToUpper(clean(tier)) {
	case "STR":
		return "STARTER"
	case "BUS":
		return "BUSINESS"
	case "ENT":
		return "ENTERPRISE"
	default:
		return strings.ToUpper(clean(tier))
	}
}

func allowedTier(tier string) bool {
\ttier = canonicalTier(tier)
\treturn tier == "STARTER" || tier == "BUSINESS" || tier == "ENTERPRISE"
}''',
)

path.write_text(text)
PY

/app/scripts/run_batch.sh
test -s /app/out/rebate_report.csv
test -s /app/out/rebate_summary.json
