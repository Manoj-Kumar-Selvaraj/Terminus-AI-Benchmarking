#!/usr/bin/env bash
set -euo pipefail

cd /app

python3 <<'PY'
from pathlib import Path

path = Path("/app/cmd/reconcile/main.go")
text = path.read_text()

text = text.replace(
    "TourType: strings.ToUpper(clean(row[4]))",
    "TourType: canonicalTourType(row[4])",
)
text = text.replace(
    "TourType: strings.ToUpper(clean(row[3]))",
    "TourType: canonicalTourType(row[3])",
)
text = text.replace(
    'func clean(value string) string {\n\treturn strings.TrimSpace(value)\n}\n\nfunc allowedTourType(tour_type string) bool {\n\ttour_type = strings.ToUpper(clean(tour_type))\n\treturn tour_type == "HARBOR" || tour_type == "SUNSET" || tour_type == "WHALE"\n}',
    '''func clean(value string) string {
\treturn strings.TrimSpace(value)
}

func canonicalTourType(tour_type string) string {
	switch strings.ToUpper(clean(tour_type)) {
	case "HBR":
		return "HARBOR"
	case "SUN":
		return "SUNSET"
	case "WHL":
		return "WHALE"
	default:
		return strings.ToUpper(clean(tour_type))
	}
}

func allowedTourType(tour_type string) bool {
\ttour_type = canonicalTourType(tour_type)
\treturn tour_type == "HARBOR" || tour_type == "SUNSET" || tour_type == "WHALE"
}''',
)

path.write_text(text)
PY

/app/scripts/run_batch.sh
test -s /app/out/credit_report.csv
test -s /app/out/credit_summary.json
