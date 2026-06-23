#!/usr/bin/env python3
"""Quick difficulty + task.toml audit for new_tasks.txt."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
tasks = [
    l.strip()
    for l in (ROOT / "new_tasks.txt").read_text(encoding="utf-8-sig").splitlines()
    if l.strip() and not l.strip().startswith("#")
]
for t in tasks:
    p = ROOT / t / "task.toml"
    if not p.exists():
        print(f"{t}: MISSING task.toml")
        continue
    text = p.read_text(encoding="utf-8")
    d = re.search(r'difficulty\s*=\s*"([^"]+)"', text)
    m = re.search(r"number_of_milestones\s*=\s*(\d+)", text)
    steps = len(re.findall(r"\[\[steps\]\]", text))
    expert = re.search(r"expert_time_estimate_min\s*=\s*(\d+)", text)
    junior = re.search(r"junior_time_estimate_min\s*=\s*(\d+)", text)
    print(
        f"{t}: difficulty={d.group(1) if d else '?'} "
        f"milestones={m.group(1) if m else '?'} steps_blocks={steps} "
        f"expert={expert.group(1) if expert else '?'} junior={junior.group(1) if junior else '?'}"
    )
