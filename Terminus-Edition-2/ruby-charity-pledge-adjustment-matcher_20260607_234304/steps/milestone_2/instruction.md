Extend the Ruby reconciler under `/app/lib` for legacy `fund` aliases while keeping all milestone 1 behavior. Normalize aliases before matching: `GEN` means `GENERAL`, `CAP` means `CAPITAL`, `REL` means `RELIEF`. Alias matching is case-insensitive and trimmed. Matched report rows must emit the canonical `fund` value, not the raw alias. Unmatched rows still leave `fund` blank.

Continue to write `/app/out/adjustment_report.csv` and `/app/out/adjustment_summary.json` with the same schemas, status labels, blank unmatched fields, and summary keys from the earlier milestone.
