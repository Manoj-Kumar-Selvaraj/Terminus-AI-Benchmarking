#!/bin/bash
set -euo pipefail
wc -l /app/data/charge_sessions.csv /app/data/session_releases.csv /app/config/windows.csv
