#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."
python3 scripts/fix_new_tasks_standards.py
