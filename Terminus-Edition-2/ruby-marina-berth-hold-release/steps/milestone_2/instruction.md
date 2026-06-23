Keep every milestone 1 rule and add legacy berth_type alias normalization. Before any comparison, trim and fold the correction `berth_type` to its canonical form: `HR` maps to `SLIP`, `QR` maps to `DRY`, and `CC` maps to `TRANSIT`. Normalize session `berth_type` the same way. From milestone 2 onward, the canonical match-eligible values are exactly `SLIP`, `DRY`, or `TRANSIT`; unknown normalized values stay unmatched even when source and correction share the same unknown value. Matched report rows must emit only the canonical session `berth_type`, never the original alias.

Milestone 2 does not use `/app/config/windows.csv`; realtime window rules begin in milestone 3. Timestamp, consumption, and tie-break rules from milestone 1 still apply: numeric 14-digit `hold_ts` and `release_ts`, `release_ts` on or after `hold_ts`, one source row consumed at most once.

Write `/app/out/berth_release_report.csv` with columns `release_id,hold_id,vessel_id,dock_id,berth_type,amount,reason,status`, preserving correction input order. Write `/app/out/berth_release_summary.txt` as `key=value` lines for `matched_count`, `matched_amount`, `unmatched_count`, and `unmatched_amount`, with amounts counted as positive integers.

The report `status` column must use only the exact strings `MATCHED` and `UNMATCHED`.
