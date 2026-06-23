The auditor must accept legacy tape labels declared by `ALIAS_*` rules in `/app/src/tape_rules.pli`. Each declaration contains `raw=>canonical`. Trim and case-fold both sides, then apply the configured mappings to catalog and audit values before comparing `block_no` and `reel_id`. Unknown values remain distinct and must not fuzzy-match.

Keep the existing full-key, state, verdict, timestamp, candidate-ordering, one-time-consumption, and audit-order behavior. Emit the selected catalog row's canonical `block_no` only for `VERIFIED`; leave it blank for `CORRUPT`.

Continue writing pipe-separated `/app/out/tape_report.csv` with header `claim_id|record_id|volume_id|reel_id|block_no|length_hash|verdict_code|status` and `/app/out/tape_summary.txt` with `verified_count`, `verified_blocks`, `corrupt_count`, and `corrupt_blocks`. Do not apply mount windows yet.
