#!/usr/bin/env bash
set -euo pipefail
/app/scripts/clean_outputs.sh
/app/scripts/compile_cobol.sh
/app/build/remit_reconcile