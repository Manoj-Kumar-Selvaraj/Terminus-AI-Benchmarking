Extend the Ruby reconciler for legacy `location` aliases while keeping the established matching and output behavior. Normalize aliases before matching: `DIN` means `DINING`, `CAF` means `CAFE`, and `MKT` means `MARKET`. Alias matching is case-insensitive and trimmed. Matched report rows must emit the canonical `location` value, not the raw alias. Unmatched rows still leave `location` blank.

Continue to write `/app/out/credit_report.csv` and `/app/out/credit_summary.json` with the established schemas, status labels, blank unmatched fields, and summary keys.
