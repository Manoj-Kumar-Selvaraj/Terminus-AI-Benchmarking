#!/usr/bin/env python3
"""Quick template-uniqueness scan for local task portfolio."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

UNIQUE_OVERRIDES = {
    "bash-coworking-room-credit-reconciler": "HIGH",
    "bash-lab-sample-credit-reconciler": "HIGH",
    "cobol-utility-return-reconciliation": "HIGH",
    "cobol-adjudicated-denial-clearing-reconciler": "HIGH",
    "cobol-brokerage-return-settlement": "HIGH",
    "cobol-municipal-return-clearing": "MED",
    "cobol-pension-contribution-reversal": "MED",
    "cobol-wire-return-settlement": "MED",
    "cobol-healthcare-return-reversal": "YES",
    "cobol-bowling-league-fee-reversal": "MED",
    "cobol-vendor-return-settlement": "MED",
    "ruby-hotel-night-audit-chargeback-router": "HIGH",
    "ruby-energy-demand-response-settler": "MED",
    "ruby-go-bash-vineyard-club-shipment-credit-router": "HIGH",
    "ruby-music-royalty-live-settlement-router": "MED",
    "ruby-courier-cod-remittance-reconciler": "HIGH",
    "ruby-ski-resort-lift-gate-release": "HIGH",
    "ruby-cloud-reservation-burst-credit-ledger": "HIGH",
    "go-live-auction-bid-reversal-ledger": "MED",
    "go-datacenter-rack-hold-release": "HIGH",
    "go-rail-yard-freight-hold-release": "HIGH",
    "go-helicopter-tour-deposit-reconciler": "MED",
    "go-citation-zone-credit-reconciler": "MED",
    "pl1-cobol-atm-risk-release-router": "HIGH",
    "pli-treasury-wire-batch-adjudicator": "HIGH",
    "pli-insurance-premium-surcharge-adjudicator": "HIGH",
    "pli-numeric-directive-rollup-processor": "HIGH",
    "pli-orbit-downlink-frame-auditor": "HIGH",
    "pli-multicurrency-ledger-clearing-processor": "HIGH",
    "pli-insurance-fnol-reserve-event-processor": "HIGH",
    "k8s-invoice-batch-rbac-recovery": "HIGH",
    "java-billing-service-container-health": "HIGH",
    "go-escape-room-booking-refund-matcher": "MAYBE",
    "ruby-subscription-seat-proration-ledger": "MAYBE",
}

SKIP_PREFIXES = (
    "Revision-",
    "submission_",
    "Old-Tasks",
    "Terminal-main",
    "chatgpt_",
    "Auto-Eval-Logs",
    ".terminus_logs",
    "scripts",
    "documentation",
)
DATE_SUFFIX = re.compile(r"_20\d{6}_\d{6}$")


def is_task_dir(path: Path) -> bool:
    return (
        path.is_dir()
        and (path / "task.toml").exists()
        and not any(path.name.startswith(prefix) for prefix in SKIP_PREFIXES)
    )


def classify(name: str) -> str:
    if name in UNIQUE_OVERRIDES:
        return UNIQUE_OVERRIDES[name]
    if name.startswith(("pli-", "pl1-", "k8s-", "java-", "bash-")):
        return "HIGH"
    if name.startswith("cobol-"):
        return "NO" if "matcher" in name else "MED"
    if name.startswith("ruby-go-bash-"):
        return "HIGH"
    if "-hold-release" in name or ("-release" in name and "matcher" not in name):
        return "HIGH"
    if any(token in name for token in ("-router", "-settler", "-processor", "-auditor", "-normalizer", "-classifier")):
        return "MED" if "matcher" not in name else "NO"
    if name.startswith(("go-", "ruby-")):
        if any(token in name for token in ("-matcher", "-reconciler", "-clearing", "-rebate-", "-adjustment-", "-refund-", "-voucher-")):
            return "NO"
    return "UNKNOWN"


def bucket(score: str) -> str:
    if score in {"HIGH", "MED", "YES"}:
        return "GE50"
    if score == "MAYBE":
        return "MAYBE"
    if score == "NO":
        return "LT50"
    return "UNKNOWN"


def summarize(label: str, names: list[str]) -> None:
    counts = {"GE50": 0, "MAYBE": 0, "LT50": 0, "UNKNOWN": 0}
    for name in names:
        counts[bucket(classify(name))] += 1
    total = len(names)
    print(f"=== {label} (n={total}) ===")
    for key in ("GE50", "MAYBE", "LT50", "UNKNOWN"):
        n = counts[key]
        pct = 100 * n / total if total else 0
        print(f"  {key}: {n} ({pct:.1f}%)")


def main() -> None:
    all_tasks = sorted(path.name for path in ROOT.iterdir() if is_task_dir(path))
    deduped = sorted(name for name in all_tasks if not DATE_SUFFIX.search(name))
    manifest = ROOT / "Revision-ChatGpt/needs_revision_pulls/portal_ids_manifest.tsv"
    portal: list[str] = []
    if manifest.exists():
        for line in manifest.read_text().splitlines():
            if line.startswith("#") or not line.strip():
                continue
            parts = line.split("\t")
            if len(parts) >= 2 and parts[1] not in {"-", ""}:
                portal.append(parts[1])
    portal = sorted(set(portal))

    summarize("ALL folders with task.toml", all_tasks)
    summarize("Deduped (no _YYYYMMDD_HHMMSS suffix)", deduped)
    summarize("Portal manifest (54 revise IDs)", portal)


if __name__ == "__main__":
    main()
