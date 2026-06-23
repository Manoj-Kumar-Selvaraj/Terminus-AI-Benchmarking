The realtime airport gate baggage hold release reconciler in `/app/cmd/reconcile/main.go` is matching correction rows to the wrong source records. Fix that Go source file so `/app/data/releases.csv` reconciles against `/app/data/holds.csv`. Keep the deliverable as a Go CLI: the verifier compiles `/app/cmd/reconcile/main.go` with the Go toolchain available at `/usr/local/go/bin/go` and then runs the produced binary.

Milestone 2 keeps every milestone 1 rule and adds legacy `check_type` alias normalization on both the holds source side and the releases correction side after trimming and case folding. Apply the alias map documented in `/app/docs/support_matrix.md` before matching. From milestone 2 onward, the canonical match-eligible `check_type` values remain exactly `MEDICAL` and `CUSTOMS`; alias codes normalize into those canonical values for matching and report output. Unknown normalized check types stay unmatched even when source and correction contain the same unknown value. Matched report rows must emit the canonical `check_type`, not the raw alias.

All milestone 1 timestamp, identity, status, reason, consumption, and ordering rules still apply. Realtime window rules from `/app/config/windows.csv` are not part of milestone 2.

Write `/app/out/baggage_release_report.csv` with columns `release_id,hold_id,bag_tag_id,gate_id,check_type,amount,reason,status`, preserving correction input order. Matched rows report the canonical source `check_type`; unmatched rows leave `check_type` blank. Write `/app/out/baggage_release_summary.txt` as `key=value` lines for `matched_count`, `matched_amount`, `unmatched_count`, and `unmatched_amount`, with amounts counted as positive integers.

The report `status` column must use only the exact strings `MATCHED` and `UNMATCHED`.
