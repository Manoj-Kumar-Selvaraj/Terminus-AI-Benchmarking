Extend `/app/cmd/reconcile/main.go` while preserving every milestone 1 through milestone 3 rule unless this milestone replaces a hardcoded list with a runtime configuration file.

Load channel aliases from `/app/config/channel_aliases.csv` (`alias,canonical`; trim and case-fold both columns). Canonical values must resolve to `ONLINE`, `MOBILE`, or `ONSITE`. Canonical names map to themselves even if omitted. Duplicate alias rows: last valid row wins. Unknown aliases stay ineligible.

Load reversal reason eligibility from `/app/config/reversal_reasons.csv` (`reason,eligible`; trim and case-fold both columns). `Y`, `YES`, `TRUE`, and `1` mean eligible; all other values mean ineligible. Duplicate reason rows: last row wins. Missing or unknown reasons are ineligible. This file replaces the hardcoded `CANCEL`, `FRAUD`, and `VOID` list.

Write `/app/out/reversal_audit.csv` with columns `session_id,channel,total_reversals,matched_count,unmatched_count,matched_amount_cents,unmatched_amount_cents`. Group by cleaned reversal `session_id` and normalized reversal channel; use `UNKNOWN` when the reversal channel does not resolve to an allowed canonical value. Sort by `session_id` then `channel`. Audit counts and amounts must reconcile with the report and summary.

Report and summary schemas stay unchanged. Matched rows still emit canonical bid channels; unmatched rows still leave report `channel` blank; each bid row is still consumed at most once.

Compile with `/usr/local/go/bin/go`.
