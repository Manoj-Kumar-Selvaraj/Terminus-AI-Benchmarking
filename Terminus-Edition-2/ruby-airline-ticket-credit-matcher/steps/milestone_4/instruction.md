Add a configuration-driven eligibility gate to `/app/lib/reconcile.rb` while preserving milestones 1-3 behavior.

Read `/app/config/methods.csv` (`fare_class,enabled`) at runtime. After alias normalization, a candidate ticket row is eligible only when its canonical `fare_class` appears in `methods.csv` with `enabled=true` (case-insensitive, whitespace-tolerant). Missing rows, malformed rows, or `enabled=false` must make that class ineligible.

This methods gate applies in both undated (legacy) and dated modes. Keep all prior requirements unchanged: exact full-id matching, consumed-row behavior, alias normalization, dated-mode fallback when date columns are absent, open-calendar gating, `credit_date <= flight_date`, latest `flight_date` tie-breaks, output schema, and positive summary totals.

Continue to write `/app/out/credit_report.csv` and `/app/out/credit_summary.json` with the same schemas, status labels, blank unmatched fields, and summary keys from the earlier milestone.
