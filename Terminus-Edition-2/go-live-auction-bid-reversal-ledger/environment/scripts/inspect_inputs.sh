#!/bin/bash
set -euo pipefail
wc -l /app/data/bids.csv /app/data/reversals.csv /app/config/session_windows.csv
