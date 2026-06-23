#!/bin/bash
set -euo pipefail
wc -l /app/data/holds.csv /app/data/releases.csv /app/config/windows.csv
