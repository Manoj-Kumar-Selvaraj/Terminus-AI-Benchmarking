#!/usr/bin/env python3
import json
import re
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
plugins = set(
    re.findall(
        r"id:\s*([A-Za-z0-9_-]+)",
        (root / "terraform/plugin-catalog.yaml").read_text(),
    )
)
jobs = json.loads((root / "terraform/jenkins_jobs.json").read_text())
trace = json.loads((root / "terraform/job_run_trace.json").read_text())
controllers = {"payments-controller", "risk-controller", "platform-controller"}

if set(jobs.get("controllers", {})) != controllers:
    print("controller set mismatch", file=sys.stderr)
    sys.exit(2)

for name, job in jobs.get("jobs", {}).items():
    ctrl = job.get("controller")
    if ctrl not in controllers:
        print("bad controller", file=sys.stderr)
        sys.exit(3)
    folder = job.get("folder")
    required_plugins = job.get("required_plugins")
    if not isinstance(folder, str) or not folder.strip():
        print("job folder missing", file=sys.stderr)
        sys.exit(4)
    if not isinstance(required_plugins, list) or not required_plugins:
        print("job plugin contract missing", file=sys.stderr)
        sys.exit(4)
    missing = set(job.get("required_plugins", [])) - plugins
    if missing:
        print("missing plugins " + repr(sorted(missing)), file=sys.stderr)
        sys.exit(5)

runs = trace.get("runs", [])
seen = []
for run in runs:
    if run.get("status") != "SUCCESS":
        print("run did not succeed", file=sys.stderr)
        sys.exit(6)
    if not isinstance(run.get("build_number"), int) or run["build_number"] <= 0:
        print("invalid build number", file=sys.stderr)
        sys.exit(6)
    seen.append((run.get("job"), run.get("controller")))
expected = {(n, j["controller"]) for n, j in jobs.get("jobs", {}).items()}
if len(seen) != len(expected) or set(seen) != expected:
    print("run trace mismatch", file=sys.stderr)
    sys.exit(6)

print(json.dumps({"ok": True, "jobs": sorted(jobs.get("jobs", {}))}))
