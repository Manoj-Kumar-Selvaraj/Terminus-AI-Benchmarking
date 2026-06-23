#!/bin/bash
set -euo pipefail
wc -l /app/data/dock_holds.csv /app/data/dock_releases.csv /app/config/windows.csv
