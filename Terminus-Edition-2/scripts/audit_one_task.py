#!/usr/bin/env python3
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from audit_all_tasks_common_issues import audit_task
from audit_fix_task_toml_timeouts import audit_only

task = Path(__file__).resolve().parents[1] / "bash-library-fine-waiver-reconciler"
print("task.toml:", audit_only(task / "task.toml") or "ok")
for issue in audit_task(task, fix=False):
    print(issue)
