#!/usr/bin/env bash
set -euo pipefail

cd /app

python3 <<'PY'
from pathlib import Path

path = Path("/app/cmd/reconcile/main.go")
text = path.read_text()

text = text.replace(
    "SeatZone: strings.ToUpper(clean(row[4]))",
    "SeatZone: canonicalSeatZone(row[4])",
)
text = text.replace(
    "SeatZone: strings.ToUpper(clean(row[3]))",
    "SeatZone: canonicalSeatZone(row[3])",
)
text = text.replace(
    'func clean(value string) string {\n\treturn strings.TrimSpace(value)\n}\n\nfunc allowedSeatZone(seat_zone string) bool {\n\tseat_zone = strings.ToUpper(clean(seat_zone))\n\treturn seat_zone == "ORCH" || seat_zone == "MEZZ" || seat_zone == "BALC"\n}',
    '''func clean(value string) string {
\treturn strings.TrimSpace(value)
}

func canonicalSeatZone(seat_zone string) string {
	switch strings.ToUpper(clean(seat_zone)) {
	case "OR":
		return "ORCH"
	case "MZ":
		return "MEZZ"
	case "BC":
		return "BALC"
	default:
		return strings.ToUpper(clean(seat_zone))
	}
}

func allowedSeatZone(seat_zone string) bool {
\tseat_zone = canonicalSeatZone(seat_zone)
\treturn seat_zone == "ORCH" || seat_zone == "MEZZ" || seat_zone == "BALC"
}''',
)

path.write_text(text)
PY

/app/scripts/run_batch.sh
test -s /app/out/voucher_report.csv
test -s /app/out/voucher_summary.json
