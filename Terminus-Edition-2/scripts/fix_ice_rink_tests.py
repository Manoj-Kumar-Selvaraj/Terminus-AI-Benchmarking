#!/usr/bin/env python3
from pathlib import Path

root = Path(__file__).resolve().parents[1] / "go-ice-rink-session-credit-matcher" / "steps"
for p in root.rglob("test_m*.py"):
    t = p.read_text(encoding="utf-8")
    if "LPRG" in t:
        t = t.replace("LPRG", "LEAG")
    t = t.replace("COMPLETED,hard", "COMPLETED,game")
    # M1 must use canonical tiers only (no alias codes on credits)
    p.write_text(t, encoding="utf-8")
print("fixed ice-rink tests")
