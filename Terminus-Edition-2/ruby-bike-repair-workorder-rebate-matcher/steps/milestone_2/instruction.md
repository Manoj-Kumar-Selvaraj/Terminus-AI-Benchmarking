Extend the Ruby reconciler for legacy `repair_type` aliases while keeping all milestone 1 behavior. Normalize aliases before matching: `TUN` means `TUNEUP`, `BRK` means `BRAKE`, `DRV` means `DRIVETRAIN`. Alias matching is case-insensitive and trimmed. Matched report rows must emit the canonical `repair_type` value, not the raw alias. Unmatched rows still leave `repair_type` blank.

Continue to write `/app/out/rebate_report.csv` and `/app/out/rebate_summary.json` with the same schemas, status labels, blank unmatched fields, and summary keys from the earlier milestone.
