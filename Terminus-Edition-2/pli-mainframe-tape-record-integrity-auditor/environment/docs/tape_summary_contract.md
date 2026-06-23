# Tape Summary Contract

`/app/out/tape_summary.txt` must contain exactly four lines in this order:

```
verified_count=<integer>
verified_blocks=<integer>
corrupt_count=<integer>
corrupt_blocks=<integer>
```

Rules:
- Each line uses `key=value` with no spaces around `=`.
- Counts are the number of `VERIFIED` and `CORRUPT` report rows.
- Block totals sum `length_hash` from the audit row as integers for each status bucket.
