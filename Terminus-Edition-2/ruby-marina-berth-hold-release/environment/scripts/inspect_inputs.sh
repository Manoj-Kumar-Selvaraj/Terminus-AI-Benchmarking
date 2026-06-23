#!/bin/bash
set -euo pipefail
wc -l /app/data/berth_holds.csv /app/data/berth_releases.csv /app/config/windows.csv
