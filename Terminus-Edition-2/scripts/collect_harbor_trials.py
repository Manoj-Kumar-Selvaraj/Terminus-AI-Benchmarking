#!/usr/bin/env python3
"""Collect Harbor job trial results for tasks in new_tasks.txt."""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JOBS = ROOT / "jobs"
LIST = ROOT / "new_tasks.txt"


def load_tasks() -> set[str]:
    return {
        line.strip()
        for line in LIST.read_text(encoding="utf-8-sig").splitlines()
        if line.strip() and not line.strip().startswith("#")
    }


def main() -> int:
    tasks = load_tasks()
    by_task: dict[str, list[dict]] = defaultdict(list)
    for path in JOBS.glob("**/result.json"):
        if path.parent.name == path.parent.parent.name:
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        name = data.get("task_name")
        if name not in tasks:
            continue
        cfg_path = path.parent / "config.json"
        agent = "unknown"
        model = None
        if cfg_path.is_file():
            cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
            agent = cfg.get("agent", {}).get("name", "unknown")
            model = cfg.get("agent", {}).get("model_name")
        steps = data.get("step_results") or []
        rewards = [
            s.get("verifier_result", {}).get("rewards", {}).get("reward")
            for s in steps
            if s.get("verifier_result")
        ]
        final = (data.get("verifier_result") or {}).get("rewards", {}).get("reward")
        by_task[name].append(
            {
                "agent": agent,
                "model": model,
                "final_reward": final,
                "step_rewards": rewards,
                "job": path.parent.parent.name,
                "trial": path.parent.name,
            }
        )

    for task in sorted(tasks):
        trials = by_task.get(task, [])
        print(f"\n{task} ({len(trials)} trials)")
        if not trials:
            print("  (no jobs/)")
            continue
        for t in trials[-5:]:
            steps = t["step_rewards"]
            step_s = ",".join(str(r) for r in steps) if steps else "—"
            print(
                f"  {t['job']} agent={t['agent']} model={t['model']} "
                f"steps=[{step_s}] final={t['final_reward']}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
