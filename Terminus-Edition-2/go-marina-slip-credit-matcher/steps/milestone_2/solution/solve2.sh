#!/usr/bin/env bash
set -euo pipefail

cd /app

python3 <<'PY'
from pathlib import Path

path = Path("/app/cmd/reconcile/main.go")
text = path.read_text()

text = text.replace(
    "DockZone: strings.ToUpper(clean(row[4]))",
    "DockZone: canonicalDockZone(row[4])",
)
text = text.replace(
    "DockZone: strings.ToUpper(clean(row[3]))",
    "DockZone: canonicalDockZone(row[3])",
)
text = text.replace(
    "DockZone: clean(row[3])",
    "DockZone: canonicalDockZone(row[3])",
)
text = text.replace(
    'func clean(value string) string {\n\treturn strings.TrimSpace(value)\n}\n\nfunc allowedDockZone(dock_zone string) bool {\n\tdock_zone = strings.ToUpper(clean(dock_zone))\n\treturn dock_zone == "NORTH" || dock_zone == "SOUTH" || dock_zone == "EAST"\n}',
    '''func clean(value string) string {
\treturn strings.TrimSpace(value)
}

func canonicalDockZone(dock_zone string) string {
	switch strings.ToUpper(clean(dock_zone)) {
	case "NZ":
		return "NORTH"
	case "SZ":
		return "SOUTH"
	case "EZ":
		return "EAST"
	default:
		return strings.ToUpper(clean(dock_zone))
	}
}

func allowedDockZone(dock_zone string) bool {
\tdock_zone = canonicalDockZone(dock_zone)
\treturn dock_zone == "NORTH" || dock_zone == "SOUTH" || dock_zone == "EAST"
}''',
)

path.write_text(text)
PY

/app/scripts/run_batch.sh
test -s /app/out/credit_report.csv
test -s /app/out/credit_summary.json
