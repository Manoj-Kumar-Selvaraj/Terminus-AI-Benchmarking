Extend the Bash reconciler for legacy `payer` aliases while keeping all milestone 1 behavior. The program still reads `/app/data/samples.csv` and `/app/data/credits.csv` and writes `/app/out/credit_report.csv` and `/app/out/credit_summary.json`.

Normalize aliases before matching: `CC` means `CARD`, `INS` means `INSURANCE`, `CA` means `CASH`. Alias matching is case-insensitive and trimmed. Matched report rows must emit the canonical `payer` value, not the raw alias. Unmatched rows still leave `payer` blank.
