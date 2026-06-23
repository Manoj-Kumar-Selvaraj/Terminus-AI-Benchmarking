Extend the Ruby reconciler for legacy `language` aliases while keeping all milestone 1 behavior. Normalize aliases before matching: `SPA` means `SPANISH`, `FRE` means `FRENCH`, `JPN` means `JAPANESE`. Alias matching is case-insensitive and trimmed. Matched report rows must emit the canonical `language` value, not the raw alias. Unmatched rows still leave `language` blank.

Continue to write `/app/out/refund_report.csv` and `/app/out/refund_summary.json` with the same schemas, status labels, blank unmatched fields, and summary keys from the earlier milestone.
