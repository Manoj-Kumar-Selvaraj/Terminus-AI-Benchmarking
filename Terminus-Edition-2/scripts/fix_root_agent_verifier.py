#!/usr/bin/env python3
"""Add root [agent] and [verifier] to task.toml when only per-step timeouts exist."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

AGENT_BLOCK = """
[agent]
timeout_sec = 1800.0

[verifier]
timeout_sec = 900.0
"""


def fix_toml(path: Path) -> bool:
    text = path.read_text(encoding="utf-8")
    if re.search(r"^\[agent\]", text, re.M):
        return False
    if "[steps.agent]" not in text:
        return False
    # insert before first [[steps]] or before [environment] if no steps header early
    if "[[steps]]" in text:
        new = text.replace("[[steps]]", AGENT_BLOCK + "\n[[steps]]", 1)
    elif "[environment]" in text:
        new = text.replace("[environment]", AGENT_BLOCK + "\n[environment]", 1)
    else:
        return False
    path.write_text(new, encoding="utf-8")
    return True


def main() -> None:
    n = 0
    for toml in sorted(ROOT.glob("*/task.toml")):
        if fix_toml(toml):
            print(f"fixed {toml.parent.name}")
            n += 1
    print(f"done {n}")


if __name__ == "__main__":
    main()
