#!/bin/bash
set -euo pipefail
wc -l /app/data/appointments.csv /app/data/claims.csv /app/config/windows.csv
