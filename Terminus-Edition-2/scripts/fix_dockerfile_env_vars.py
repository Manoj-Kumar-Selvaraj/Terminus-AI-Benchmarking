#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TASKS = [
    "go-aquarium-pass-credit-matcher",
    "go-bike-share-trip-credit-matcher",
    "go-carwash-subscription-rebate-matcher",
    "go-catering-order-adjustment-matcher",
    "go-datacenter-rack-hold-release",
    "go-device-warranty-claim-matcher",
    "go-escape-room-booking-refund-matcher",
    "go-lab-sample-chain-reassignment",
    "go-live-auction-bid-reversal-ledger",
    "go-marketplace-payout-matcher",
    "go-travel-booking-adjustment-matcher",
    "go-utility-refund-reconciler",
    "go-warehouse-pickwave-shortage-matcher",
    "go-waterpark-pass-refund-matcher",
]

for task in TASKS:
    p = ROOT / task / "environment" / "Dockerfile"
    if not p.is_file():
        continue
    text = p.read_text(encoding="utf-8")
    text = text.replace("${{GO_VERSION}}", "${GO_VERSION}")
    text = text.replace("${{GO_SHA256}}", "${GO_SHA256}")
    text = text.replace("${{PATH}}", "${PATH}")
    p.write_text(text, encoding="utf-8")
    print(f"fixed {task}")
