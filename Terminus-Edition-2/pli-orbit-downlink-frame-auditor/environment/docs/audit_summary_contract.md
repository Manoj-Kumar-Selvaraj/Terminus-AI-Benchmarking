# Audit Summary Contract

`/app/out/audit_summary.txt` must contain exactly four lines in this order:

```
matched_count=<integer>
matched_frames=<integer>
rejected_count=<integer>
rejected_frames=<integer>
```

Rules:
- Each line uses `key=value` with no spaces around `=`.
- Counts are the number of `ACCEPTED` and `REJECTED` report rows.
