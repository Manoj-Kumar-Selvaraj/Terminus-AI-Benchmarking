All input records are fixed-width 64-byte lines. Positions are 1-based byte offsets.

## Wire record (`wires.dat`)

| Bytes | Field | Notes |
|------:|-------|-------|
| 1 | record type | Always `W` |
| 2–13 | wire_id | 12 characters |
| 14–16 | reason | 3-character wire reason code |
| 17–26 | amount_cents | 10-digit zero-padded cents |
| 27–34 | account_id | 8 characters |
| 35 | status | `S` = settled |
| 36–43 | settlement_date | Optional `YYYYMMDD`; required for milestone 3+ date gates when present |

## Return record (`returns.dat`)

| Bytes | Field | Notes |
|------:|-------|-------|
| 1 | record type | Always `R` |
| 2–13 | wire_id | 12 characters |
| 14–23 | amount_cents | 10-digit zero-padded cents |
| 24–31 | account_id | 8 characters |
| 32–39 | return_date | Optional `YYYYMMDD`; required for milestone 3+ date gates when present |

Milestone 1 and 2 inputs omit the trailing date fields. Milestone 3 and later may include them on both files.

## cycle_calendar.txt

One line per date: `YYYYMMDD STATUS` where STATUS is compared case-insensitively to `OPEN` (for example `20260501 OPEN`).

## wire_return_report.csv

Header row required. Columns: `wire_id,account_id,reason,amount_cents,status`. Status is `CLEARED` or `EXCEPTION`. EXCEPTION rows use an empty `reason` field.
