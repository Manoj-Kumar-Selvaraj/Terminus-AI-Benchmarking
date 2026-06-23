#!/bin/bash
set -euo pipefail
wc -l /app/data/picks.csv /app/data/shortages.csv /app/config/windows.csv
