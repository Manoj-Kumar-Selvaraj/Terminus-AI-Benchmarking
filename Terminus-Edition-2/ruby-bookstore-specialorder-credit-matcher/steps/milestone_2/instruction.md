Extend the Ruby reconciler for legacy `section` aliases while keeping all milestone 1 behavior. Normalize aliases before matching: `FIC` means `FICTION`, `TXT` means `TEXTBOOK`, `COM` means `COMIC`. Alias matching is case-insensitive and trimmed. Matched report rows must emit the canonical `section` value, not the raw alias. Unmatched rows still leave `section` blank.

Continue to write `/app/out/credit_report.csv` and `/app/out/credit_summary.json` with the same schemas, status labels, blank unmatched fields, and summary keys from the earlier milestone.
