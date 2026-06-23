Add aisle-level audit output to the rack hold release reconciler under `/app` while preserving every milestone 1 through milestone 3 rule unless this milestone explicitly adds a new output file.

Keep writing `/app/out/rack_release_report.csv`, `/app/out/rack_release_summary.txt`, and `/app/out/rack_release_rejections.csv` with the same schemas, ordering, alias behavior, window behavior, rejection precedence, and summary accounting from earlier milestones.

Add `/app/out/rack_release_audit.csv` with columns `aisle_id,total_releases,matched_count,unmatched_count,matched_amount,unmatched_amount`. Include one row for every `aisle_id` that appears in the correction input, sorted by `aisle_id` ascending as plain strings. `total_releases` counts all correction rows for that aisle. `matched_count` and `unmatched_count` count report statuses for that aisle. Derive `matched_amount` and `unmatched_amount` from the report rows for that aisle using the same canonical amount rules as milestone 2: sum only valid canonical positive integer strings, and treat invalid unmatched correction amounts as `0`.

The audit totals must reconcile with the global summary: the sum of all audit matched and unmatched counts and amounts must equal `/app/out/rack_release_summary.txt`. Input files may be overwritten at runtime with large batches, duplicate source candidates, dynamic aliases, overlapping windows, invalid amounts, malformed timestamps, closed windows, missing windows, and consumed candidates. Do not hardcode fixture ids or assume the bundled CSV size.

Keep the deliverable as a Go CLI compiled from the source under `/app` with `/usr/local/go/bin/go`.
