The warehouse pickwave shortage reconciler in `/app/cmd/reconcile/main.go` is matching correction rows to the wrong pick records. Fix that Go source file so `/app/data/shortages.csv` reconciles against `/app/data/picks.csv`. Milestone 2 keeps every milestone 1 rule and adds legacy `kind` alias normalization. Normalize aliases after trimming and case folding before matching: `EA` means `EACH`, `CS` means `CASE`, `PL` means `PALLET`. From milestone 2 onward, the canonical match-eligible `kind` values expand to exactly `EACH`, `CASE`, and `PALLET`; `PALLET` is newly eligible in this milestone. Unknown normalized kinds stay unmatched even when source and correction contain the same unknown value. Matched report rows must emit the canonical `kind`, not the raw alias.

All milestone 1 timestamp, identity, status, reason, consumption, and ordering rules still apply. Realtime window rules from `/app/config/windows.csv` are not part of milestone 2.

Input schemas:
- `/app/data/picks.csv`: `pick_id,sku,wave_id,kind,amount,source_ts,status,location`
- `/app/data/shortages.csv`: `action_id,pick_id,sku,wave_id,kind,amount,action_ts,reason,location`

Write `/app/out/shortage_report.csv` with columns `action_id,pick_id,sku,wave_id,kind,amount,reason,status`, preserving correction input order. Matched rows report the canonical source `kind`; unmatched rows leave `kind` blank. Write `/app/out/shortage_summary.txt` as `key=value` lines for `matched_count`, `matched_amount`, `unmatched_count`, and `unmatched_amount`, with amounts counted as positive integers.

The report `status` column must use only the exact strings `MATCHED` and `UNMATCHED`.
