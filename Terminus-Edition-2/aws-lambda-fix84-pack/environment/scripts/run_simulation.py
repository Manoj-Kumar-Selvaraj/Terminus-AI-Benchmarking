#!/usr/bin/env python3
"""Compatibility launcher for the Go offline simulator.

Before each probe, the local deployment controller reconciles generated mapping
and role-policy artifacts. The Go simulator is rebuilt when its source changes,
so source repairs are exercised by the normal command surface.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def main() -> None:
    app = Path(os.environ.get("APP_ROOT", "/app"))
    env = os.environ.copy()
    env["APP_ROOT"] = str(app)

    reconcile = app / "control_plane" / "reconcile.mjs"
    subprocess.run(["node", str(reconcile)], cwd=app, env=env, check=True)

    simulator = app / "simulator"
    cache_dir = app / "tmp"
    cache_dir.mkdir(parents=True, exist_ok=True)
    binary = cache_dir / "run_simulation-current"
    sources = list(simulator.glob("*.go")) + [simulator / "go.mod"]
    newest_source = max(path.stat().st_mtime_ns for path in sources)
    if not binary.exists() or binary.stat().st_mtime_ns < newest_source:
        subprocess.run(
            ["go", "build", "-trimpath", "-o", str(binary), "."],
            cwd=simulator,
            env=env,
            check=True,
        )
    os.execve(str(binary), [str(binary), *sys.argv[1:]], env)


if __name__ == "__main__":
    main()
