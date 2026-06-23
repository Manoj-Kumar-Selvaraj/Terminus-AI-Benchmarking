#!/bin/bash
set -euo pipefail
wc -l /app/data/sessions.csv /app/data/adjustments.csv /app/config/windows.csv
