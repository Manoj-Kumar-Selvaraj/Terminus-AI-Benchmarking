#!/usr/bin/env python3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from scaffold_fresh_batch_20260602 import restore_tests_from_escape_room
from scaffold_go_tasks_from_bike import TASKS

LOAD = {
    "go-photo-booth-print-credit-matcher": ("loadPrintes", "loadPrints"),
    "go-helicopter-tour-deposit-reconciler": ("loadTourDeposites", "loadTourDeposits"),
}

for slug, (typo, fix) in LOAD.items():
    spec = dict(next(s for s in TASKS if s["slug"] == slug))
    spec["load_typo"], spec["load_fix"] = typo, fix
    restore_tests_from_escape_room(ROOT / slug, spec)
    print("restored", slug)
