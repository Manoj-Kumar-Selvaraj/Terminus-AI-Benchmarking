Keep every milestone 1 rule and add legacy care_room alias normalization. Before any comparison, trim and fold the correction `care_room` to its canonical form: `HR` maps to `ACUTE`, `QR` maps to `OBS`, and `CC` maps to `ICU`. Normalize session `care_room` the same way. From milestone 2 onward, the canonical match-eligible values are exactly `ACUTE`, `OBS`, or `ICU`; unknown normalized values stay unmatched even when source and correction share the same unknown value. Matched report rows must emit only the canonical session `care_room`, never the original alias.

Window, timestamp, consumption, and tie-break rules from milestone 1 still apply: source `hold_ts` inside an `OPEN` window, `release_ts` on or after `hold_ts` and on or before window `close_ts`, one source row consumed at most once, latest `hold_ts` then earliest source row.

Write `/app/out/bed_release_report.csv` with columns `release_id,hold_id,patient_id,ward_id,care_room,amount,reason,status`, preserving correction input order. Write `/app/out/bed_release_summary.txt` as `key=value` lines for `matched_count`, `matched_amount`, `unmatched_count`, and `unmatched_amount`, with amounts counted as positive integers.

The report `status` column must use only the exact strings `MATCHED` and `UNMATCHED`.
