#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
bash "$SCRIPT_DIR/solve1.sh"

cd /app

python3 <<'PY'
from pathlib import Path

path = Path("/app/cmd/reconcile/main.go")
text = path.read_text()

if "func canonicalPassType(pass_type string)" in text:
    raise SystemExit(0)

text = text.replace(
    "PassType: strings.ToUpper(clean(row[4]))",
    "PassType: canonicalPassType(row[4])",
)
text = text.replace(
    "PassType: strings.ToUpper(clean(row[3]))",
    "PassType: canonicalPassType(row[3])",
)
text = text.replace(
    'func clean(value string) string {\n\treturn strings.TrimSpace(value)\n}\n\nfunc allowedPassType(pass_type string) bool {\n\tpass_type = strings.ToUpper(clean(pass_type))\n\treturn pass_type == "GENERAL" || pass_type == "SPECIAL" || pass_type == "MEMBER"\n}',
    'func clean(value string) string {\n\treturn strings.TrimSpace(value)\n}\n\nfunc canonicalPassType(pass_type string) string {\n\tswitch strings.ToUpper(clean(pass_type)) {\n\tcase "GN":\n\t\treturn "GENERAL"\n\tcase "SP":\n\t\treturn "SPECIAL"\n\tcase "MB":\n\t\treturn "MEMBER"\n\tdefault:\n\t\treturn strings.ToUpper(clean(pass_type))\n\t}\n}\n\nfunc allowedPassType(pass_type string) bool {\n\tpass_type = canonicalPassType(pass_type)\n\treturn pass_type == "GENERAL" || pass_type == "SPECIAL" || pass_type == "MEMBER"\n}',
)

path.write_text(text)
PY

/app/scripts/run_batch.sh
test -s /app/out/museum_credit_report.csv
test -s /app/out/museum_credit_summary.json
