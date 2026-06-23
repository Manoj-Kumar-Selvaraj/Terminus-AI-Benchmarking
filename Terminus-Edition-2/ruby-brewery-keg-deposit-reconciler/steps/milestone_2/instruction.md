Extend the Ruby reconciler for legacy `keg_type` aliases while keeping all milestone 1 behavior. Normalize aliases before matching: `HLF` means `HALF`, `SIX` means `SIXTH`, `COR` means `CORNELIUS`. Alias matching is case-insensitive and trimmed. Matched report rows must emit the canonical `keg_type` value, not the raw alias. Unmatched rows still leave `keg_type` blank.

Continue to write `/app/out/deposit_report.csv` and `/app/out/deposit_summary.json` with the same schemas, status labels, blank unmatched fields, and summary keys from the earlier milestone.
