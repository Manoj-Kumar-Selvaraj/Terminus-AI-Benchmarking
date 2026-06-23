#!/bin/bash
set -euo pipefail
wc -l /app/data/seat_events.csv /app/data/credits.csv /app/config/windows.csv
