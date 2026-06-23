from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any


def handle_batch(event: dict[str, Any]) -> dict[str, Any]:
    app_root = Path(os.environ.get("APP_ROOT", "/app"))
    invoke = app_root / "handler" / "invoke.mjs"
    proc = subprocess.run(
        ["node", str(invoke)],
        input=json.dumps(event),
        text=True,
        capture_output=True,
        env=os.environ.copy(),
        cwd=str(app_root),
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr or proc.stdout or "handler invocation failed")
    return json.loads(proc.stdout)
