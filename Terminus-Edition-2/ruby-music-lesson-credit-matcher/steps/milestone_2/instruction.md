Extend the Ruby reconciler for legacy `instrument` aliases while keeping all milestone 1 behavior. Normalize aliases before matching: `PNO` means `PIANO`, `GTR` means `GUITAR`, `VLN` means `VIOLIN`. Alias matching is case-insensitive and trimmed. Matched report rows must emit the canonical `instrument` value, not the raw alias. Unmatched rows still leave `instrument` blank.

Continue to write `/app/out/credit_report.csv` and `/app/out/credit_summary.json` with the same schemas, status labels, blank unmatched fields, and summary keys from the earlier milestone.
