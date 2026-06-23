# Record layouts

All statement and control-total records are fixed width. Offsets are one-based.

## Statement input (`*.stm`, 48 bytes)

| Offset | Length | Field        | Notes                          |
|--------|--------|--------------|--------------------------------|
| 1      | 1      | type         | Literal `S`                    |
| 2      | 8      | account_id   | Account identifier             |
| 10     | 8      | stmt_date    | `YYYYMMDD`                     |
| 18     | 5      | seq_no       | Sequence within account/date   |
| 23     | 2      | txn_type     | `DR` debit or `CR` credit      |
| 25     | 10     | amount_cents | Zero-padded integer cents      |
| 35     | 14     | stream_tag   | Source sort-run label          |

**Composite business key** (ordering): bytes 2–22 (`account_id` + `stmt_date` + `seq_no`).

**Control group key** (totals): bytes 2–17 (`account_id` + `stmt_date`).

Each sort-run file must be non-decreasing on the composite business key.

## Control total output (`/app/out/control_totals.dat`, 56 bytes)

| Offset | Length | Field        | Notes                          |
|--------|--------|--------------|--------------------------------|
| 1      | 1      | type         | Literal `T`                    |
| 2      | 8      | account_id   |                                |
| 10     | 8      | stmt_date    |                                |
| 18     | 10     | debit_cents  | Sum of `DR` amounts in group   |
| 28     | 10     | credit_cents | Sum of `CR` amounts in group   |
| 38     | 10     | stmt_count   | Statement rows in group        |
| 48     | 1      | status       | `C` committed                  |
| 49     | 8      | filler       | Spaces                         |

Rows appear in merge processing order. Only committed groups are written.

## Checkpoint file (`/app/out/checkpoint.dat`, 110 bytes)

| Offset | Length | Field              |
|--------|--------|--------------------|
| 1      | 21     | last_committed_key |
| 22     | 2      | last_file_num      |
| 24     | 6      | last_record_num    |
| 30     | 8      | statement_rows     |
| 38     | 10     | pending_debit      |
| 48     | 10     | pending_credit     |
| 58     | 10     | pending_count      |
| 68     | 16     | pending_group_key  |
| 84     | 6      | committed_groups   |
| 90     | 10     | total_debit_cents  |
| 100    | 10     | total_credit_cents |

When no checkpoint exists the file is absent or all spaces.

## Merge summary (`/app/out/merge_summary.txt`)

Key/value lines:

- `committed_groups`
- `total_debit_cents`
- `total_credit_cents`
- `statement_rows`
- `checkpoint_commits`

All values are non-negative base-10 integers.
