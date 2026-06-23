#!/bin/bash
set -euo pipefail
wc -l /app/data/appointments.csv /app/data/warranty_claims.csv /app/config/windows.csv
