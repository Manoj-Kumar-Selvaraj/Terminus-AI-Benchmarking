#!/bin/bash
set -euo pipefail
wc -l /app/data/appointments.csv /app/data/adjustments.csv /app/config/windows.csv
