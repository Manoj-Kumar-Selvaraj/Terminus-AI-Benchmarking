#!/usr/bin/env bash
set -euo pipefail
test -s /app/config/methods.csv
test -s /app/config/fund_aliases.json
test -s /app/config/report_schema.json
ruby -rjson -e 'JSON.parse(File.read("/app/config/fund_aliases.json"))'
ruby -rjson -e 'JSON.parse(File.read("/app/config/report_schema.json"))'
echo "config lint ok"
