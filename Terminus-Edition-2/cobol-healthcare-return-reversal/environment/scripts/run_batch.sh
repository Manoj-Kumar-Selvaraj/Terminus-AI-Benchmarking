#!/usr/bin/env bash
set -euo pipefail
/app/scripts/clean_outputs.sh
/app/scripts/compile.sh
/app/build/batch