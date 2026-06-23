Reports preserve input order and keep amount_cents in the raw input representation.

`/app/out/chargeback_summary.txt` is a key-value text file with exactly `applied_count`, `applied_amount_cents`, `exception_count`, and `exception_amount_cents`. Counts and cents are non-negative decimal integers, and applied and exception cents are counted as positive amounts.
