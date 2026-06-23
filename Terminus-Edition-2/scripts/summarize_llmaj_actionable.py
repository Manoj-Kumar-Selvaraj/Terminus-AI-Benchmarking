#!/usr/bin/env python3
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKIP = {"anti_cheating_measures", "test_deps_in_image"}
REPORT = ROOT / "reworked-tasks-v2" / "llmaj-reports"


def main() -> None:
    tasks: list[str] = []
    for f in ("new-tasks/completed_llmaj_batch_1.txt", "new-tasks/completed_llmaj_batch_2.txt"):
        for line in Path(ROOT / f).read_text(encoding="utf-8").splitlines():
            t = line.strip()
            if t and not t.startswith("#"):
                tasks.append(t)
    for t in tasks:
        p = REPORT / f"{t}_strict_llmaj.json"
        if not p.is_file():
            print(f"{t}: NO REPORT")
            continue
        checks = json.loads(p.read_text(encoding="utf-8"))["checks"]
        fails = [n for n, item in checks.items() if n not in SKIP and item["outcome"] == "fail"]
        status = "PASS" if not fails else "FAIL"
        detail = ", ".join(fails) if fails else "ok"
        print(f"{t}: {status} [{detail}]")


if __name__ == "__main__":
    main()
