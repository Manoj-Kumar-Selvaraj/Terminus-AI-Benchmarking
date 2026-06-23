#!/bin/bash
set -euo pipefail
wc -l /app/data/locker_holds.csv /app/data/locker_releases.csv /app/config/windows.csv
