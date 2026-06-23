# Remittance output contract

The batch writes three artifacts under `/app/out/`. Normative field definitions live in `/app/config/payload_schema.json`.

## COBOL export (`remit_export.csv`)

- Header (exact): `transaction_id,account_id,rail,amount_cents,business_date`
- One row per exported remittance, in input order among exported rows only.
- `amount_cents` stays the 10-character zero-padded text from the input record (not re-formatted).

## COBOL summary (`remit_summary.txt`)

Three `key=value` lines (integers, no surrounding spaces):

- `exported_count` - number of rows written to `remit_export.csv`
- `exported_amount_cents` - positive sum of exported amounts in cents (must not be negated)
- `rejected_count` - input records rejected by the COBOL filter (non-posted, disallowed rail, etc.)

## Java payload (`remit_payload.json`)

Top-level counters plus a `transactions` array in **export row order** (same order as `remit_export.csv`).

Each transaction object:

| Field | Type | Notes |
|-------|------|-------|
| `transaction_id` | string | From export |
| `account_id` | string | From export |
| `rail` | string | From export |
| `amount_cents` | string | 10-character zero-padded, unchanged from export |
| `business_date` | string | `YYYYMMDD` from export |
| `status` | string | `ACCEPTED`, `REJECTED`, `DUPLICATE`, or `CLOSED_DATE` (milestone 3) |

Summary fields:

- `accepted_count` / `accepted_amount_cents` - only `ACCEPTED` rows
- `rejected_count` - every non-`ACCEPTED` transaction (including `REJECTED`, `DUPLICATE`, `CLOSED_DATE`)
