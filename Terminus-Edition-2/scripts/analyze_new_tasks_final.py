#!/usr/bin/env python3
"""Aggregate strict LLMaJ, difficulty metadata, and agent-trial hints for new_tasks.txt."""
from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LIST = ROOT / "new_tasks.txt"
REPORTS = ROOT / "reworked-tasks-v2" / "llmaj-reports"
LOGS = ROOT / ".terminus_logs"
OUT = ROOT / "new-tasks" / "FINAL_ANALYSIS.md"
IGNORE_LLMaj = {"anti_cheating_measures", "test_deps_in_image"}


def load_tasks() -> list[str]:
    return [
        line.strip()
        for line in LIST.read_text(encoding="utf-8-sig").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]


def aggregate_actionable() -> dict[str, int]:
    both: dict[str, int] = {}
    for task in load_tasks():
        lj = llmaj_summary(task)
        if not lj:
            continue
        for name in lj["both_models"]:
            both[name] = both.get(name, 0) + 1
    return both


def read_toml_field(task: str, field: str) -> str | None:
    path = ROOT / task / "task.toml"
    if not path.is_file():
        return None
    text = path.read_text(encoding="utf-8")
    m = re.search(rf"^{field}\s*=\s*\"([^\"]+)\"", text, re.M)
    return m.group(1) if m else None


def milestone_count(task: str) -> int | None:
    path = ROOT / task / "task.toml"
    if not path.is_file():
        return None
    text = path.read_text(encoding="utf-8")
    m = re.search(r"number_of_milestones\s*=\s*(\d+)", text)
    return int(m.group(1)) if m else None


def llmaj_summary(task: str) -> dict | None:
    path = REPORTS / f"{task}_strict_llmaj.json"
    if not path.is_file():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    models = data.get("models", [])
    fails = [n for n, c in data["checks"].items() if c["outcome"] == "fail"]
    actionable = [n for n in fails if n not in IGNORE_LLMaj]
    both = []
    for name in actionable:
        by = data["checks"][name].get("by_model", {})
        if models and all(by.get(m, {}).get("outcome") == "fail" for m in models):
            both.append(name)
    strict_pass = len(fails) == 0
    harbor_pass = len(actionable) == 0
    return {
        "strict_pass": strict_pass,
        "harbor_pass": harbor_pass,
        "fails": fails,
        "actionable": actionable,
        "both_models": both,
        "mtime": datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc),
    }


def harbor_trials(task: str) -> list[dict]:
    jobs = ROOT / "jobs"
    out: list[dict] = []
    if not jobs.is_dir():
        return out
    for path in jobs.glob("**/result.json"):
        if path.parent.name == path.parent.parent.name:
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if data.get("task_name") != task:
            continue
        cfg = path.parent / "config.json"
        agent = "unknown"
        if cfg.is_file():
            agent = json.loads(cfg.read_text(encoding="utf-8")).get("agent", {}).get("name", "unknown")
        steps = data.get("step_results") or []
        rewards = [
            s.get("verifier_result", {}).get("rewards", {}).get("reward")
            for s in steps
            if s.get("verifier_result")
        ]
        final = (data.get("verifier_result") or {}).get("rewards", {}).get("reward")
        out.append({"agent": agent, "steps": rewards, "final": final, "job": path.parent.parent.name})
    return out


def format_trials(trials: list[dict]) -> str:
    if not trials:
        return "no Harbor jobs/"
    real = [t for t in trials if t["agent"] not in ("oracle", "nop")]
    if real:
        latest = real[-1]
        steps = latest.get("steps") or []
        ok = sum(1 for r in steps if r is not None and float(r) >= 0.99)
        return f"{latest['agent']}: {ok}/{len(steps)} milestones @ reward=1 (job {latest['job']})"
    latest = trials[-1]
    steps = latest.get("steps") or []
    step_s = ",".join(str(s) for s in steps) if steps else "—"
    if latest["agent"] == "oracle":
        if steps and all(float(s or 0) >= 0.99 for s in steps):
            return f"oracle only: 3/3 pass (job {latest['job']})"
        return f"oracle only: steps=[{step_s}] final={latest.get('final')} — not full pass"
    return f"{latest['agent']}: steps=[{step_s}]"


def main() -> int:
    tasks = load_tasks()
    rows: list[dict] = []
    for task in tasks:
        lj = llmaj_summary(task)
        trials = harbor_trials(task)
        rows.append(
            {
                "task": task,
                "difficulty": read_toml_field(task, "difficulty"),
                "milestones": milestone_count(task),
                "llmaj": lj,
                "agent_trials": format_trials(trials),
                "trial_count": len(trials),
            }
        )

    lines = [
        "# New tasks final analysis (23)",
        "",
        f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        "",
        "## Summary",
        "",
    ]
    with_report = sum(1 for r in rows if r["llmaj"])
    harbor_ok = sum(1 for r in rows if r["llmaj"] and r["llmaj"]["harbor_pass"])
    strict_ok = sum(1 for r in rows if r["llmaj"] and r["llmaj"]["strict_pass"])
    lines.append(f"- Tasks: {len(rows)}")
    lines.append(f"- LLMaJ reports on disk: {with_report}/{len(rows)}")
    lines.append(f"- Strict LLMaJ all criteria pass: {strict_ok}/{with_report or '—'}")
    lines.append(f"- Harbor-actionable pass (excl. anti_cheat + test_deps): {harbor_ok}/{with_report or '—'}")
    both_agg = aggregate_actionable()
    if both_agg:
        lines.append("- Both-models actionable failure counts:")
        for name, count in sorted(both_agg.items(), key=lambda x: -x[1]):
            lines.append(f"  - `{name}`: {count}/{len(rows)} tasks")
    lines.append("")

  # Difficulty table
    lines.extend(["## Difficulty (`task.toml`)", "", "| Task | difficulty | milestones |", "|------|------------|------------|"])
    for r in rows:
        lines.append(f"| {r['task']} | {r['difficulty'] or '?'} | {r['milestones'] or '?'} |")
    lines.append("")

    lines.extend(
        [
            "## Strict LLMaJ (actionable failures)",
            "",
            "Ignored for Harbor pass: `anti_cheating_measures`, `test_deps_in_image`.",
            "",
            "| Task | harbor OK | actionable | both-models agree |",
            "|------|-----------|------------|-------------------|",
        ]
    )
    for r in rows:
        lj = r["llmaj"]
        if not lj:
            lines.append(f"| {r['task']} | — | no report | — |")
            continue
        ok = "yes" if lj["harbor_pass"] else "no"
        act = ", ".join(lj["actionable"]) if lj["actionable"] else "—"
        both = ", ".join(lj["both_models"]) if lj["both_models"] else "—"
        lines.append(f"| {r['task']} | {ok} | {act} | {both} |")
    lines.append("")

    lines.extend(["## Agent trials (instruction sufficiency proxy)", ""])
    has_real_agents = any("oracle only" not in r["agent_trials"] and "no Harbor" not in r["agent_trials"] for r in rows)
    lines.append(
        "**Real-agent trials (GPT-5.2 / Opus 4.6) are required to validate `difficulty = hard`.** "
        "Current `jobs/` data is almost entirely **oracle** smoke runs, not model attempts."
    )
    lines.append("")
    lines.extend(["| Task | Harbor jobs | signal |", "|------|-------------|--------|"])
    for r in rows:
        lines.append(f"| {r['task']} | {r['trial_count']} | {r['agent_trials']} |")
    if not has_real_agents:
        lines.append("")
        lines.append(
            "Recommended: `RUN_REAL_AGENTS=1 AGENT_TRIALS=3` via `terminus2_cli` on a representative "
            "subset (Go matcher, Go hold-release, Ruby hold-release, PL/I) before platform submit."
        )
    lines.append("")

    lines.extend(["## Per-task instruction sufficiency notes", ""])
    for r in rows:
        lj = r["llmaj"]
        lines.append(f"### {r['task']}")
        if not lj:
            lines.append("- No strict LLMaJ report; run `python scripts/run_llmaj_litellm.py {r['task']} --strict`")
        elif lj["harbor_pass"]:
            lines.append("- LLMaJ: no actionable failures (platform-fixed items may still fail strict).")
        else:
            for name in lj["both_models"] or lj["actionable"]:
                path = REPORTS / f"{r['task']}_strict_llmaj.json"
                detail = json.loads(path.read_text(encoding="utf-8"))
                expl = detail["checks"][name].get("explanation", "")[:280]
                lines.append(f"- **{name}** (both models): {expl}…")
        lines.append(f"- Declared difficulty: `{r['difficulty']}` — validate with real-agent pass rate (target ≤20% for hard).")
        lines.append("")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
