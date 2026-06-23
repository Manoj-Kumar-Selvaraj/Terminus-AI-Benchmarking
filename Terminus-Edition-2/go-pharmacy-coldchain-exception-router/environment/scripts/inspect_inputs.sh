#!/bin/bash
set -euo pipefail
wc -l /app/data/accessions.csv /app/data/exceptions.csv /app/config/windows.csv
