Extend the rack hold release reconciler under `/app` while preserving every milestone 1 and milestone 2 rule and output schema.

Apply realtime window rules from `/app/config/windows.csv`. The source timestamp must fall inside an `OPEN` window for the same `aisle_id`, and the correction timestamp must be on or after the source timestamp but not after the close timestamp of that same qualifying window. Window state matching for `OPEN` is case-insensitive. Multiple `OPEN` windows for the same aisle may overlap; allow a match when source and correction fit within at least one valid window. Closed, missing, malformed, or unlisted windows are not eligible and must not poison other valid rows for the same aisle.

When multiple unused source rows qualify, choose the latest source timestamp; if source timestamps tie, choose the earliest source input row. Exact duplicate source rows may still be consumed independently by row position.

If either timestamp is non-numeric or non-14-digit, the row is ineligible even when a corresponding window row exists and is marked `OPEN`. When every otherwise eligible unused source candidate fails because `release_ts` is earlier than that candidate's source timestamp, reject with `NO_ELIGIBLE_SOURCE`; that ordering failure is not a window problem. Use `WINDOW_INELIGIBLE` only when at least one otherwise eligible unused source exists but no valid open window covers the timestamp pair.

Also write `/app/out/rack_release_rejections.csv` with columns `release_id,code` for every unmatched correction in correction input order. Use the first applicable code from this precedence list: `BAD_RELEASE_AMOUNT`, `BAD_RELEASE_TS`, `BAD_REASON`, `NO_SOURCE_IDENTITY`, `NO_ELIGIBLE_SOURCE`, `WINDOW_INELIGIBLE`. Invalid correction amounts such as `0104`, `+100`, or `0` map to `BAD_RELEASE_AMOUNT`. `NO_SOURCE_IDENTITY` means no source row shares the full `hold_id`, `asset_id`, `aisle_id`, `rack`, and canonical amount. Matched corrections must not appear in the rejection file.

Keep the deliverable as a Go CLI compiled from the source under `/app` with `/usr/local/go/bin/go`.
