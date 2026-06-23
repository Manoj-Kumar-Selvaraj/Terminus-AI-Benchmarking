Extend the Ruby reconciler for legacy `load_type` aliases while keeping all milestone 1 behavior. Normalize aliases before matching: `SOL` means `SOIL`, `MUL` means `MULCH`, `PLT` means `PLANTS`. Alias matching is case-insensitive and trimmed. Matched report rows must emit the canonical `load_type` value, not the raw alias. Unmatched rows still leave `load_type` blank.

Continue to write `/app/out/refund_report.csv` and `/app/out/refund_summary.json` with the same schemas, status labels, blank unmatched fields, and summary keys from the earlier milestone.
