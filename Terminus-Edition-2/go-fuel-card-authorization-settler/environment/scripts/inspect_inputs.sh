#!/bin/bash
set -euo pipefail
wc -l /app/data/authorizations.csv /app/data/reversals.csv /app/config/windows.csv
