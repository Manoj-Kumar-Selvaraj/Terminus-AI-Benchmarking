Extend the Ruby reconciler for legacy `bay` aliases while keeping all milestone 1 behavior. Normalize aliases before matching: `EXP` means `EXPRESS`, `STD` means `STANDARD`, `DTL` means `DETAIL`. Alias matching is case-insensitive and trimmed. Matched report rows must emit the canonical `bay` value, not the raw alias. Unmatched rows still leave `bay` blank.

Continue to write `/app/out/rebate_report.csv` and `/app/out/rebate_summary.json` with the same schemas, status labels, blank unmatched fields, and summary keys from the earlier milestone.
