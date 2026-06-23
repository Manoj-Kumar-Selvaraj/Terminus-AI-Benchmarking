Directive sequence discipline and cross-claim netting are not applied. Extend the PL/I control deck so `/app/scripts/run_batch.sh` enforces monotonic sequence consumption and zero weighted netting before downstream acceptance.

Preserve all prior milestone behavior.

Directives may carry optional `seq_no`; accumulators may carry optional `expected_seq`. A roll matches only when `expected_seq` equals the directive `seq_no` and no lower unused sequence exists for the same `stream_id|canonical_segment_id` slot.

Accumulators may carry optional `netting_key`. All rows sharing a netting key must net to weighted total zero before downstream acceptance; partial or non-zero groups produce `NETTING_HOLD` exceptions and downgrade affected rolled rows to `SKIPPED` with blank `segment_id`. Netting is evaluated after all group rows are seen.

Write `/app/out/rollup_exceptions.csv` for netting holds when sequence mode is on, using the same pipe-delimited `claim_id|line_id|stream_id|reason|detail` schema introduced in milestone 3.
