#!/bin/bash
set -euo pipefail
wc -l /app/data/holds.csv \
  /app/data/disbursements.csv \
  /app/config/windows.csv \
  /app/config/closing_packages.csv \
  /app/data/trust_balances.csv \
  /app/config/control_totals.csv
