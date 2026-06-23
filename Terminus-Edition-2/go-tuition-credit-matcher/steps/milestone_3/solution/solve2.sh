#!/usr/bin/env bash
set -euo pipefail

cd /app

python3 <<'PY'
from pathlib import Path

path = Path("/app/cmd/reconcile/main.go")
text = path.read_text()

text = text.replace(
    "Term: strings.ToUpper(clean(row[4]))",
    "Term: canonicalTerm(row[4])",
)
text = text.replace(
    "Term: strings.ToUpper(clean(row[3]))",
    "Term: canonicalTerm(row[3])",
)
text = text.replace(
    'func clean(value string) string {\n\treturn strings.TrimSpace(value)\n}\n\nfunc allowedTerm(term string) bool {\n\tterm = strings.ToUpper(clean(term))\n\treturn term == "ONL" || term == "MAIL" || term == "CAMP"\n}',
    '''func clean(value string) string {
\treturn strings.TrimSpace(value)
}

func canonicalTerm(term string) string {
	switch strings.ToUpper(clean(term)) {
	case "WEB":
		return "ONL"
	case "PST":
		return "MAIL"
	case "OFF":
		return "CAMP"
	default:
		return strings.ToUpper(clean(term))
	}
}

func allowedTerm(term string) bool {
\tterm = canonicalTerm(term)
\treturn term == "ONL" || term == "MAIL" || term == "CAMP"
}''',
)

path.write_text(text)
PY

/app/scripts/run_batch.sh
test -s /app/out/credit_report.csv
test -s /app/out/credit_summary.json
