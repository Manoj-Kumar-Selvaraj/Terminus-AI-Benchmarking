Extend the reconciler to support legacy `sku_type` aliases while preserving every existing identity, status, reason, timestamp, window, source-consumption, candidate-ordering, and output rule.

After trimming and case folding, map `C` to `CPU`, `GPUF` to `GPU`, and `MEMORY` to `MEM`. The canonical eligible values are now `CPU`, `GPU`, and `MEM`. Normalize source and correction values before eligibility checks. Unknown values stay unmatched even when both rows share the same unknown token.

The normalized `sku_type` is still not a pairwise matching key: eligible source and correction rows may have different canonical values. Matched report rows emit the selected source's canonical value, while unmatched rows leave `sku_type` blank.

Continue writing `/app/out/seat_credit_report.csv` and `/app/out/seat_credit_summary.txt` using the previously documented schemas, correction order, exact status labels, and positive integer totals.
