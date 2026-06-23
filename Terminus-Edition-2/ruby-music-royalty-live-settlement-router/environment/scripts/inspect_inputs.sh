#!/bin/bash
set -euo pipefail
wc -l /app/data/holds.csv /app/data/settlements.csv /app/config/windows.csv
