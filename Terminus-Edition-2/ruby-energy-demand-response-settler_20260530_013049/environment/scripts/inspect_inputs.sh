#!/bin/bash
set -euo pipefail
wc -l /app/data/events.csv /app/data/settlements.csv /app/config/windows.csv
