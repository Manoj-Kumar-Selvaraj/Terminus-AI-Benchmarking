#!/usr/bin/env python3
"""Summarize strict LLMaJ JSON reports."""

import json
import sys
from pathlib import Path

IGNORE = {"anti_cheating_measures", "test_deps_in_image"}


def main() -> int:
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent.parent / "reworked-tasks-v2" / "llmaj-reports"
    for path in sorted(root.glob("*_strict_llmaj.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        fails = [name for name, item in data["checks"].items() if item["outcome"] == "fail"]
        actionable = [name for name in fails if name not in IGNORE]
        both = [
            name
            for name in actionable
            if all(
                str(data["checks"][name]["by_model"].get(model, {}).get("outcome", "")).lower() == "fail"
                for model in data["models"]
            )
        ]
        print(f"{data['task']}: {len(fails)} fail ({len(actionable)} actionable, {len(both)} both-models)")
        if actionable:
            print(f"  actionable: {', '.join(actionable)}")
        if both:
            print(f"  both agree: {', '.join(both)}")
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
