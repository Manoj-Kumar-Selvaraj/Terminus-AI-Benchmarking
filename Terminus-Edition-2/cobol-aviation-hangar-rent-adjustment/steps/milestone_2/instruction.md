Extend `/app/src/hangar_adjust_reconcile.cbl` to normalize legacy action hangar classes before matching:

- `PM` means `PRM`
- `ST` means `STD`
- `EC` means `ECO`

Matched report rows emit the canonical source class. Unmatched rows leave `hangar_class` blank as an empty CSV field, never an alias or space padding. Preserve full record, account, amount, branch, status, reason, date, and class gates; one-time source-row consumption; action input order; report schema; summary totals; and the exact `MATCHED` and `UNMATCHED` status values.

When duplicate actions target one source row, the earliest eligible action consumes it.
