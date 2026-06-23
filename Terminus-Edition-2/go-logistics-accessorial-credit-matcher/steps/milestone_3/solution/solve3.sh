#!/usr/bin/env bash
set -euo pipefail
# Milestone 3 date rules are implemented in milestone_2/solve2.sh; solve.sh chains prior milestones.
/app/scripts/run_batch.sh
test -s /app/out/credit_report.csv
test -s /app/out/credit_summary.json
