#!/bin/bash
set -euo pipefail
wc -l /app/data/accessions.csv /app/data/reassignments.csv /app/config/windows.csv
