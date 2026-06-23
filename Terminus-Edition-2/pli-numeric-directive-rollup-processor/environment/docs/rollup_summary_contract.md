# Rollup Summary Contract

`/app/out/rollup_summary.txt` must contain exactly four lines in this order:

```
rolled_count=<integer>
rolled_total_cents=<integer>
skipped_count=<integer>
skipped_total_cents=<integer>
```

Rules:
- Each line uses `key=value` with no spaces around `=`.
- Counts are the number of `ROLLED` and `SKIPPED` report rows.
- Cent totals sum `value_cents` from the accumulator row as integers for each status bucket.
