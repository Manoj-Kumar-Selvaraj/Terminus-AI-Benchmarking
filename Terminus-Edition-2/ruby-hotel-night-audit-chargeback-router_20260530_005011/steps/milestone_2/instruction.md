The realtime hotel night audit chargeback reconciler is matching correction rows to the wrong source records. Fix it so `/app/data/chargebacks.csv` reconciles against `/app/data/folios.csv`, using `/app/config/windows.csv` for the active realtime window rules.

A correction can match only when the full `folio_id`, `guest_id`, `property_id`, `location`, `amount` all match, the source status is the literal `POSTED`, the correction reason is `DISPUTE`, `DUPLICATE`, `NOAUTH`, the `kind` field is one of the canonical values `CARD`, or `CASH`, both timestamps are numeric, the correction timestamp `action_ts` is on or after the source timestamp `source_ts`, and the source row has not already been consumed.

Write `/app/out/chargeback_report.csv` with columns `action_id,folio_id,guest_id,property_id,kind,amount,reason,status`, preserving correction input order. Matched rows report the canonical source `kind`; unmatched rows leave `kind` blank. Write `/app/out/chargeback_summary.txt` as `key=value` lines for `matched_count`, `matched_amount`, `unmatched_count`, and `unmatched_amount`, with amounts counted as positive integers.

A correction can match only when the full `folio_id`, `guest_id`, `property_id`, `location`, and `amount` all match, the source status is the literal `POSTED`, the correction reason is `DISPUTE`, `DUPLICATE`, or `NOAUTH`, the `kind` is one of `CARD`, `CASH`, or `POINTS` after alias normalization, both timestamps are numeric, the correction timestamp is on or after the source timestamp, and the source row has not already been consumed.

Write `/app/out/chargeback_report.csv` with columns `action_id,folio_id,guest_id,property_id,kind,amount,reason,status`, preserving correction input order. Matched rows report the canonical source `kind`; unmatched rows leave `kind` blank. Write `/app/out/chargeback_summary.txt` as `key=value` lines for `matched_count`, `matched_amount`, `unmatched_count`, and `unmatched_amount`, with amounts counted as positive integers.

Milestone 2 keeps every milestone 1 rule and adds the documented legacy kind aliases. Normalize aliases after trimming and case folding before matching, validate the normalized value through the same matching gates, and emit only the canonical kind values in matched report rows. Unknown kinds stay unmatched without changing the output schema or status labels.

The report `status` column must use only the exact strings `MATCHED` and `UNMATCHED`.
