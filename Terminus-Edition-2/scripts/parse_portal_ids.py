#!/usr/bin/env python3
"""Parse portal_ids_clean.txt into manifest TSV."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "Revision-ChatGpt" / "needs_revision_pulls"
UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)

ALIASES = {
    "ruby-music-royalty-live-settlement-ledger": "ruby-music-royalty-live-settlement-router",
    "ruby-parking-garage-session-refund-matcher": "ruby-parking-garage-session-adjustment-clearing",
    "go-live-auction-bid-reversal-matcher": "go-live-auction-bid-reversal-ledger",
    "pl1-cobol-atm-risk-release-reconciler": "pl1-cobol-atm-risk-release-router",
    "ruby-cooking-class-voucher-refund-matcher": "ruby-cooking-class-voucher-matcher",
    "ruby-go-bash-vineyard-club-credit-ledger": "ruby-go-bash-vineyard-club-shipment-credit-router",
    "cobol-escrow-return-reconciler": "cobol-escrow-return-reconciliation",
}
FITNESS = {
    "78816498-a2d8-41ae-acd8-d42d80405961",
    "57f23c91-035f-4b52-b6a4-bae742212e3d",
    "cdefb68f-ab0e-4909-be1d-3fa153b88a4a",
    "529e2a84-f140-4036-98c2-64f45fa72f31",
    "02ce0a54-ea1c-4339-ab60-f8dcb36411d8",
}
PORTAL_NAMES = {
    "d0295913-57b4-4d22-ae74-449c845df95e": "ruby-campus-meal-plan-credit-matcher",
    "7224d09b-53e1-4d83-a0ca-d607d8abc3ac": "cobol-utility-meter-adjustment-router",
    "b00c48ef-6543-45f3-82e9-9d219b93ebab": "ruby-hotel-night-audit-charge-matcher",
    "e3c6b347-3559-4612-abe1-8ebb1776afc0": "ruby-stadium-concession-refund-matcher",
    "60af763d-1e5c-4df4-9a0a-84c313ef7e55": "go-telemetry-incident-credit-reconciler",
    "ce854f97-e916-46b0-b5a7-1f64cac9d49c": "ruby-energy-demand-response-credit-router",
    "4e43bc9d-ff68-44d2-bb3d-2957f1e5bbad": "go-farmers-market-stall-refund-matcher",
    "c55be376-df97-4f0a-922e-ebf1e17a000d": "go-pharmacy-coldchain-exception-router",
}


def main() -> None:
    ids = [
        ln.strip()
        for ln in (OUT / "portal_ids_clean.txt").read_text(encoding="utf-8").splitlines()
        if UUID.match(ln.strip())
    ]
    mapped: dict[str, str] = {}
    for line in (ROOT / "needs_revision_mapped.txt").read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            sid, plat = line.split(None, 1)
            mapped[sid] = ALIASES.get(plat, plat)

    rows: list[str] = []
    counts: dict[str, int] = {}
    for sid in ids:
        folder = mapped.get(sid) or PORTAL_NAMES.get(sid, "")
        local = bool(folder and (ROOT / folder).is_dir())
        if sid in FITNESS:
            status = "FITNESS_SKIP"
        elif local:
            status = "LOCAL_OK"
        elif folder:
            status = "NO_LOCAL_FOLDER"
        else:
            status = "UNMAPPED"
        counts[status] = counts.get(status, 0) + 1
        rows.append(f"{sid}\t{folder or '-'}\t{status}")

    (OUT / "portal_ids_manifest.tsv").write_text(
        "# submission_id\tlocal_folder\tstatus\n" + "\n".join(rows) + "\n",
        encoding="utf-8",
    )
    for k, v in sorted(counts.items()):
        print(f"{k}: {v}")


if __name__ == "__main__":
    main()
