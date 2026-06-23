Extend the Ruby reconciler for legacy `arrangement` aliases while keeping all milestone 1 behavior. Normalize aliases before matching: `BQT` means `BOUQUET`, `CTR` means `CENTERPIECE`, `ARC` means `ARCH`. Alias matching is case-insensitive and trimmed. Matched report rows must emit the canonical `arrangement` value, not the raw alias. Unmatched rows still leave `arrangement` blank.

Continue to write `/app/out/credit_report.csv` and `/app/out/credit_summary.json` with the same schemas, status labels, blank unmatched fields, and summary keys from the earlier milestone.
