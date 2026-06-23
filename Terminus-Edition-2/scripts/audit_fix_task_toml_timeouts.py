#!/usr/bin/env python3
"""Audit and fix mandatory task.toml timeout/environment settings."""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AGENT_TIMEOUT = 1800.0
VERIFIER_TIMEOUT = 900.0
BUILD_TIMEOUT = 900.0
ENV_LINES = [
    "allow_internet = false",
    f"build_timeout_sec = {BUILD_TIMEOUT}",
    "cpus = 2",
    "memory_mb = 4096",
    "storage_mb = 10240",
]


def parse_milestones(text: str) -> int:
    names = re.findall(r"^\s*name\s*=\s*\"milestone_\d+\"", text, re.M)
    if names:
        return len(names)
    m = re.search(r"number_of_milestones\s*=\s*(\d+)", text)
    return int(m.group(1)) if m else 1


def ensure_top_level_timeouts(text: str) -> str:
    agent_block = f"\n[agent]\ntimeout_sec = {int(AGENT_TIMEOUT)}\n"
    verifier_block = f"\n[verifier]\ntimeout_sec = {int(VERIFIER_TIMEOUT)}\n"

    if not re.search(r"^\[agent\]", text, re.M):
        insert_at = text.find("\n[environment]")
        if insert_at == -1:
            insert_at = text.find("\n[[steps]]")
        if insert_at == -1:
            text = text.rstrip() + agent_block + verifier_block.lstrip()
        else:
            text = text[:insert_at] + agent_block + verifier_block + text[insert_at:]
    else:
        text = re.sub(
            r"(^\[agent\]\s*\n)timeout_sec\s*=\s*[\d.]+",
            rf"\1timeout_sec = {int(AGENT_TIMEOUT)}",
            text,
            count=1,
            flags=re.M,
        )
    if not re.search(r"^\[verifier\]", text, re.M):
        pass  # added with agent above
    else:
        text = re.sub(
            r"(^\[verifier\]\s*\n)timeout_sec\s*=\s*[\d.]+",
            rf"\1timeout_sec = {int(VERIFIER_TIMEOUT)}",
            text,
            count=1,
            flags=re.M,
        )
    return text


def ensure_environment(text: str) -> str:
    env_body = "\n".join(ENV_LINES)
    workdir = 'workdir = "/app"'
    if re.search(r"^\[environment\]", text, re.M):
        text = re.sub(
            r"\[environment\][^\[]*",
            f"[environment]\n{env_body}\n{workdir}\n",
            text,
            count=1,
            flags=re.S,
        )
    else:
        insert_at = text.find("\n[agent]")
        if insert_at == -1:
            insert_at = text.find("\n[[steps]]")
        block = f"\n[environment]\n{env_body}\n{workdir}\n"
        text = text[:insert_at] + block + text[insert_at:] if insert_at != -1 else text + block
    return text


def ensure_step_timeouts(text: str, milestones: int) -> str:
    step_block = (
        "[[steps]]\n"
        'name = "milestone_{n}"\n\n'
        "[steps.agent]\n"
        f"timeout_sec = {AGENT_TIMEOUT}\n"
        "[steps.verifier]\n"
        f"timeout_sec = {VERIFIER_TIMEOUT}\n"
    )

    if "[[steps]]" not in text:
        steps = "".join(step_block.format(n=i) for i in range(1, milestones + 1))
        text = text.rstrip() + "\n" + steps
        return text

  # Normalize every [steps.agent] and [steps.verifier] block
    text = re.sub(
        r"(\[steps\.agent\]\s*\n)timeout_sec\s*=\s*[\d.]+",
        rf"\1timeout_sec = {AGENT_TIMEOUT}",
        text,
    )
    text = re.sub(
        r"(\[steps\.verifier\]\s*\n)timeout_sec\s*=\s*[\d.]+",
        rf"\1timeout_sec = {VERIFIER_TIMEOUT}",
        text,
    )

    # Add missing verifier/agent under steps that lack them
    def fix_step_section(match: re.Match[str]) -> str:
        block = match.group(0)
        if "[steps.agent]" not in block:
            block = block.rstrip() + (
                f"\n\n[steps.agent]\ntimeout_sec = {AGENT_TIMEOUT}\n"
                f"[steps.verifier]\ntimeout_sec = {VERIFIER_TIMEOUT}\n"
            )
        elif "[steps.verifier]" not in block:
            block = block.rstrip() + f"\n[steps.verifier]\ntimeout_sec = {VERIFIER_TIMEOUT}\n"
        return block

    text = re.sub(
        r"\[\[steps\]\][^\[]*?(?=\[\[steps\]\]|\[agent\]|\[verifier\]|\[environment\]|\Z)",
        fix_step_section,
        text,
        flags=re.S,
    )
    return text


def fix_task_toml(path: Path) -> tuple[bool, list[str]]:
    original = path.read_text(encoding="utf-8")
    text = original.replace("\r\n", "\n")
    notes: list[str] = []
    milestones = parse_milestones(text)

    if "[environment]" not in text or "allow_internet = false" not in text:
        notes.append("environment")
    if not re.search(r"^\[agent\]", text, re.M):
        notes.append("top-level agent")
    if not re.search(r"^\[verifier\]", text, re.M):
        notes.append("top-level verifier")

    text = ensure_environment(text)
    text = ensure_top_level_timeouts(text)
    text = ensure_step_timeouts(text, milestones)

    if text != original.replace("\r\n", "\n"):
        path.write_text(text if text.endswith("\n") else text + "\n", encoding="utf-8", newline="\n")
        return True, notes
    return False, notes


def audit_only(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    problems: list[str] = []
    env = re.search(r"\[environment\](.*?)(?=\n\[|\n\[\[|\Z)", text, re.S)
    if not env:
        problems.append("missing [environment]")
    else:
        body = env.group(1)
        if "allow_internet = false" not in body:
            problems.append("allow_internet")
        if not re.search(r"build_timeout_sec\s*=\s*(600|900)", body):
            problems.append("build_timeout_sec")
        for key, val in [("cpus", "2"), ("memory_mb", "4096"), ("storage_mb", "10240")]:
            if not re.search(rf"{key}\s*=\s*{val}", body):
                problems.append(key)
    if not re.search(r"^\[agent\]", text, re.M):
        problems.append("[agent]")
    elif not re.search(r"^\[agent\][\s\S]*?timeout_sec\s*=\s*1800", text, re.M):
        problems.append("agent timeout")
    if not re.search(r"^\[verifier\]", text, re.M):
        problems.append("[verifier]")
    elif not re.search(r"^\[verifier\][\s\S]*?timeout_sec\s*=\s*900", text, re.M):
        problems.append("verifier timeout")
    for t in re.findall(r"\[steps\.agent\][\s\S]*?timeout_sec\s*=\s*([\d.]+)", text):
        if float(t) != AGENT_TIMEOUT:
            problems.append(f"steps.agent={t}")
    for t in re.findall(r"\[steps\.verifier\][\s\S]*?timeout_sec\s*=\s*([\d.]+)", text):
        if float(t) != VERIFIER_TIMEOUT:
            problems.append(f"steps.verifier={t}")
    if "[[steps]]" in text and not re.search(r"\[steps\.agent\]", text):
        problems.append("missing steps.agent")
    return problems


def main() -> int:
    dry_run = "--dry-run" in sys.argv
    changed = 0
    remaining: list[tuple[str, list[str]]] = []

    for path in sorted(ROOT.glob("*/task.toml")):
        if dry_run:
            probs = audit_only(path)
            if probs:
                remaining.append((path.parent.name, probs))
            continue
        was_changed, _ = fix_task_toml(path)
        if was_changed:
            changed += 1
        probs = audit_only(path)
        if probs:
            remaining.append((path.parent.name, probs))

    if dry_run:
        print(f"Would fix tasks with issues: {len(remaining)}")
    else:
        print(f"Updated task.toml files: {changed}")

    if remaining:
        print(f"Still non-compliant: {len(remaining)}")
        for name, probs in remaining[:20]:
            print(f"  {name}: {', '.join(probs)}")
        if len(remaining) > 20:
            print(f"  ... and {len(remaining) - 20} more")
        return 1

    print("All tasks compliant.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
