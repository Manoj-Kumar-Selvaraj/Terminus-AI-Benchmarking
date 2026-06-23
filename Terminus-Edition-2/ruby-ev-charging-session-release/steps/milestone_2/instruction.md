Keep every milestone 1 rule and add legacy rate_plan alias normalization. Before any comparison, trim and fold the correction `rate_plan` to its canonical form: `HR` maps to `LEVEL2`, `QR` maps to `DCFC`, and `CC` maps to `FLEET`. Normalize session `rate_plan` the same way. From milestone 2 onward, the canonical match-eligible values are exactly `LEVEL2`, `DCFC`, or `FLEET`; unknown normalized values stay unmatched even when source and correction share the same unknown value. Matched report rows must emit only the canonical session `rate_plan`, never the original alias.

Timestamp ordering and consumption rules from milestone 1 still apply: `release_ts` must be numeric and on or after numeric source `plug_ts`, and one source row can be consumed at most once. Realtime window rules are introduced in milestone 3, not milestone 2.

Write `/app/out/ev_release_report.csv` with columns `release_id,session_id,vehicle_id,station_id,rate_plan,amount,reason,status`, preserving correction input order. Write `/app/out/ev_release_summary.txt` as `key=value` lines for `matched_count`, `matched_amount`, `unmatched_count`, and `unmatched_amount`, with amounts counted as positive integers.

The report `status` column must use only the exact strings `MATCHED` and `UNMATCHED`.
