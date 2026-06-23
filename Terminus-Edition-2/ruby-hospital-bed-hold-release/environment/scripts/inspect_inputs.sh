#!/bin/bash
set -euo pipefail
wc -l /app/data/bed_holds.csv /app/data/bed_releases.csv /app/config/windows.csv
