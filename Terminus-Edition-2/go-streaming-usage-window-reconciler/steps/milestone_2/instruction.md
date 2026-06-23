Continue the streaming usage credit reconciler in `/app/cmd/reconcile/main.go`. Keep every milestone 1 rule: full `stream_id` equality, matching `account_id`, `region`, and `minutes`, playback status `POSTED`, eligible credit reasons `BUFFER`, `DUPLICATE`, and `OUTAGE`, numeric timestamps with `event_utc` on or after playback `end_utc` and within the region's open cutoff, single-use playback rows, and latest-`end_utc` selection with earliest-row tie-breaking.

Milestone 2 makes the legacy device aliases explicit. Normalize credit and playback devices using `/app/config/device_aliases.csv` (`TV` to `CTV`, `PHONE` to `MOBILE`, `WEBAPP` to `BROWSER`) after trimming and case folding before any comparison. Matched report rows must emit the canonical playback device (`CTV`, `MOBILE`, or `BROWSER`), never the raw alias. Unknown devices stay unmatched.

Keep the milestone 1 output contract: `/app/out/usage_credit_report.csv` with columns `credit_id,stream_id,account_id,device,minutes,reason,status`, and `/app/out/usage_credit_summary.txt` with `matched_count`, `matched_minutes`, `unmatched_count`, and `unmatched_minutes`. Preserve credit input order and use only `MATCHED` or `UNMATCHED` status labels.

Keep the deliverable as a Go CLI: the verifier compiles with `/usr/local/go/bin/go` and runs the produced binary.
