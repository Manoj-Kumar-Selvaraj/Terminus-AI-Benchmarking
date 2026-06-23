# Enterprise billing record layouts

All batch files are fixed width and are processed under `/app`.

## Usage input (`*.usg`, 52 bytes)

| Offset | Length | Field | Notes |
|--------|--------|-------|-------|
| 1 | 1 | type | Literal `U` |
| 2 | 8 | account_id | Billing account |
| 10 | 6 | batch_id | Source usage batch |
| 16 | 4 | sequence | Row sequence in batch |
| 20 | 10 | amount_cents | Positive integer cents |
| 30 | 4 | service_code | Usage service |
| 34 | 19 | filler | Spaces |

The approval tier is selected from the account aggregate total, not from an individual usage row.

## Prior ledger (`/app/config/prior_ledger.dat`, 40 bytes)

| Offset | Length | Field |
|--------|--------|-------|
| 1 | 1 | type, literal `P` |
| 2 | 8 | account_id |
| 10 | 6 | batch_id |
| 16 | 10 | invoice_id |
| 26 | 10 | amount_cents |
| 36 | 5 | filler |

A batch is a duplicate only when both `account_id` and `batch_id` match.

## Invoice register (`/app/out/invoice_register.dat`, 72 bytes)

| Offset | Length | Field |
|--------|--------|-------|
| 1 | 1 | type, literal `I` |
| 2 | 8 | account_id |
| 10 | 10 | invoice_no |
| 20 | 10 | total_cents |
| 30 | 10 | approval_tier |
| 40 | 16 | stages |
| 56 | 8 | status |
| 64 | 9 | filler |

### Stage label conventions

The `approval_tier` field reflects the threshold selected from the account aggregate total. The `stages` field and approval trace rows use these labels:

| Tier | `approval_tier` | `stages` | Approval trace rows |
|------|-----------------|----------|---------------------|
| AUTO | `AUTO` | `AUTO` | none |
| REGIONAL | `REGIONAL` | `REGIONAL` | one `REGIONAL` row with result `PASS` |
| DUAL (milestone 1) | `DUAL` | `REGIONAL` | one `REGIONAL` row with result `PASS` |
| DUAL (milestone 3+) | `DUAL` | `REGIONAL+FINANCE` | `REGIONAL` then `FINANCE`, both `PASS` |

## Approval trace (`/app/out/approval_trace.dat`, 40 bytes)

| Offset | Length | Field |
|--------|--------|-------|
| 1 | 1 | type, literal `T` |
| 2 | 8 | account_id |
| 10 | 8 | stage |
| 18 | 8 | result |
| 26 | 15 | filler |

## Billing summary (`/app/out/billing_summary.txt`)

The summary uses `key=value` lines for `invoices_posted`, `total_billed_cents`, `usage_rows`, `duplicate_batches_blocked`, and `checkpoint_commits`.

## Restart checkpoint (`/app/out/checkpoint.dat`, 138 bytes)

| Offset | Length | Field |
|--------|--------|-------|
| 1 | 2 | manifest file number |
| 3 | 6 | record number within that file |
| 9 | 8 | pending account id |
| 17 | 10 | pending account total cents |
| 27 | 6 | pending account usage count |
| 33 | 10 | last committed invoice number |
| 43 | 6 | processed row count |
| 49 | 6 | total usage rows |
| 55 | 6 | invoices posted |
| 61 | 12 | total billed cents |
| 73 | 6 | duplicate batches blocked |
| 79 | 2 | pending account batch count |
| 81 | 10 | last usage amount cents |
| 91 | 48 | eight 6-byte pending batch ids |

Restart retains already written invoice and trace rows, skips input through the saved file and record position, and resumes the pending account state.
