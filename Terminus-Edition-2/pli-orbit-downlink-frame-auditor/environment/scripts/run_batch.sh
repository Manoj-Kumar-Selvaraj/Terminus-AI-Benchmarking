#!/bin/bash
set -euo pipefail
gawk -f /app/scripts/pli_audit.awk
