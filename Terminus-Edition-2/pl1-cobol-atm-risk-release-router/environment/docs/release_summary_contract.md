# Release Summary Contract

`/app/out/release_summary.txt` contains exactly four lines in this order, each formatted as `key=value` with no spaces around `=`:

```
matched_count=<non-negative integer>
matched_amount_cents=<non-negative integer>
unmatched_count=<non-negative integer>
unmatched_amount_cents=<non-negative integer>
```

Do not emit JSON, YAML, colon-separated labels, or other formats.
