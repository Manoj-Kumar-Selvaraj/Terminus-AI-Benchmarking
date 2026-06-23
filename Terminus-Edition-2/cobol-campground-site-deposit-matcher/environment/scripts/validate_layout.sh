#!/usr/bin/env bash
set -euo pipefail
python3 - <<'PY'
from pathlib import Path
for path in [Path('/app/data/site_fees.dat'), Path('/app/data/deposit_returns.dat')]:
    for idx, line in enumerate(path.read_text().splitlines(), 1):
        if len(line) < 47:
            raise SystemExit(f'{path}:{idx}: fixed-width record too short')
print('layout ok')
PY
