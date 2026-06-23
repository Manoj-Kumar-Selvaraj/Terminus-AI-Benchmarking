The remittance router under `/app` has a bad COBOL-to-Java handoff. RTP remittances are missing from `/app/out/remit_export.csv`, the COBOL export summary amount is signed backwards, and the Java adapter cannot reach the local rules service when it runs inside Docker Compose.

Fix `/app/src/remit_reconcile.cbl` and `/app/java/RemittanceAdapter.java` so `/app/scripts/run_all.sh` reads `/app/data/remittances.dat`, writes `/app/out/remit_export.csv` and `/app/out/remit_summary.txt`, calls the rules service from `RULES_URL` when it is reachable, and writes `/app/out/remit_payload.json`. Output shapes are defined in `/app/config/payload_schema.json` and `/app/docs/payload_contract.md`.

**COBOL export (`remit_export.csv`)** - Header: `transaction_id,account_id,rail,amount_cents,business_date`. Posted `ACH`, `WIR`, and `RTP` records are exportable; `CHK` and non-posted records are rejected before the Java adapter. Keep `amount_cents` as the 10-character zero-padded text from the input record.

**COBOL summary (`remit_summary.txt`)** - Three lines: `exported_count=`, `exported_amount_cents=`, `rejected_count=`. Counts must match the export. `exported_amount_cents` must be the **positive** sum of exported amounts in cents (fix the current sign inversion).

**Java payload (`remit_payload.json`)** - One transaction object per export row (same order), with fields and statuses per the schema. The verifier runs the adapter without the Compose `rules` service, so the Java adapter must tolerate a failed or unresolved rules-service call by falling back to the allowed rails in `/app/config/rails.csv`: `ACH`, `WIR`, and `RTP` are allowed, while `CHK` is not. Do not let an unavailable rules service crash the batch.
