#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="$ROOT/revision-custom-rubrics"
mkdir -p "$OUT"
python3 - "$ROOT" <<'PY'
import sys
from pathlib import Path

ROOT = Path(sys.argv[1])
OUT = ROOT / "revision-custom-rubrics"
sys.path.insert(0, str(ROOT / "scripts"))
from fix_custom_revisions_batch import all_tasks

for folder in all_tasks():
    rp = ROOT / folder / "rubric.txt"
    if rp.is_file():
        (OUT / f"{folder}.rubric.txt").write_text(
            rp.read_text(encoding="utf-8"), encoding="utf-8"
        )
        print(f"synced {folder}")
PY
