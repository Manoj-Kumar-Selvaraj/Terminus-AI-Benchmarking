#!/bin/bash
set -euo pipefail
wc -l /app/data/deliveries.csv /app/data/remittances.csv /app/config/windows.csv
