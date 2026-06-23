Fix the live auction bid reversal reconciler in `/app/cmd/reconcile/main.go`. Read `/app/data/bids.csv` and `/app/data/reversals.csv`, then write `/app/out/reversal_report.csv` and `/app/out/reversal_summary.txt`. Do not use legacy channel aliases or dynamic reason configuration.

A reversal matches a bid only when cleaned `bid_id`, `bidder_id`, `session_id`, `lot_id`, and zero-padded `amount_cents` are exactly equal; bid status is `ACCEPTED` (case-insensitive); reversal reason is `CANCEL`, `FRAUD`, or `VOID`; and both channels are the same canonical value among `ONLINE`, `MOBILE`, and `ONSITE`. `WEB`, `APP`, `FLOOR`, and any other non-canonical channel are ineligible.

Malformed, blank, signed, decimal, zero, or negative `amount_cents` fails the amount gate and never matches. Both `event_ts` values must be 14-digit numerics. Bid `event_ts` must fall inside an `OPEN` window for the same `session_id` in `/app/config/session_windows.csv` (trimmed, case-insensitive `state`; inclusive `open_ts` and `close_ts`). Reversal `event_ts` must be on or after bid `event_ts` and not after window `close_ts`. Closed, missing, malformed, or unlisted windows are ineligible.

Each bid row is consumed at most once. When multiple unused bids qualify, choose the first qualifying row in file order.

Write `/app/out/reversal_report.csv` with columns `reversal_id,bid_id,bidder_id,session_id,channel,amount_cents,reason,status`. Emit one row per reversal in reversal input order and preserve reversal `amount_cents` text. Use exactly `MATCHED` or `UNMATCHED`. Matched rows emit the canonical bid `channel`; unmatched rows leave `channel` blank.

Write `/app/out/reversal_summary.txt` as `key=value` lines for `matched_count`, `matched_amount_cents`, `unmatched_count`, and `unmatched_amount_cents`. `matched_amount_cents` sums positive integer cents only from `MATCHED` rows with eligible amounts. `unmatched_amount_cents` sums positive integer cents only from `UNMATCHED` rows whose `amount_cents` parses as a positive integer; ineligible amount formats contribute `0` to both amount totals while still appearing as `UNMATCHED` in the report.

Compile with `/usr/local/go/bin/go`.
