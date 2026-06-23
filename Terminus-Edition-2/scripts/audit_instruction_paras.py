#!/usr/bin/env python3
from pathlib import Path

TASKS = [
    "ruby-charity-pledge-adjustment-matcher",
    "go-farmers-market-stall-refund-matcher",
    "cobol-hospital-claim-denial-reconciler",
    "go-waterpark-pass-refund-matcher",
    "go-logistics-accessorial-credit-matcher",
    "ruby-cloud-reservation-burst-credit-ledger",
    "ruby-parking-garage-session-adjustment-clearing",
    "go-device-warranty-claim-matcher",
    "go-pharmacy-coldchain-exception-router",
]

root = Path(__file__).resolve().parent.parent
for task in TASKS:
    base = root / task / "steps"
    if not base.exists():
        print(f"MISSING {task}")
        continue
    for inst in sorted(base.glob("milestone_*/instruction.md")):
        text = inst.read_text(encoding="utf-8").strip()
        paras = [p for p in text.split("\n\n") if p.strip()]
        flags = []
        if len(paras) > 3:
            flags.append(f"{len(paras)}paras")
        if "verifier compiles" in text.lower():
            flags.append("verifier")
        if "For this milestone," in text:
            flags.append("For-this-milestone")
        if "SUM-LINE" in text or "broken logic" in text.lower():
            flags.append("reveals-defect")
        if flags:
            print(f"{task}/{inst.parent.name}: {';'.join(flags)}")
