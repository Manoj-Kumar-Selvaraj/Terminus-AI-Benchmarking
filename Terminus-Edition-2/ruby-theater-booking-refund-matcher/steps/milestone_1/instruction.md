Fix the Ruby reconciler in `/app/lib/reconcile.rb`. Run it through `/app/scripts/run_batch.sh`, which reads `/app/data/bookings.csv` and `/app/data/refunds.csv`, then writes `/app/out/refund_report.csv` and `/app/out/refund_summary.json`.

A refund matches a booking only when `booking_id`, `patron_id`, `amount_cents`, `TICKETED` booking status, and `seat_zone` all line up. Compare `booking_id` values as full identifiers (shared prefixes are not sufficient). Allowed `seat_zone` values are `ORCH`, `MEZZ`, and `BALC`; the refund `seat_zone` must equal the booking `seat_zone` after normalization (two different allowed zones do not match each other). Trim incidental surrounding spaces on input fields; compare status and `seat_zone` case-insensitively.

Each booking input row may be consumed by at most one refund. If multiple refunds could match the same booking, only the earliest refund in input order that finds an eligible booking should consume it.

The report schema is `booking_id,patron_id,seat_zone,amount_cents,status` with one row per refund in refund input order. Use `MATCHED` or `UNMATCHED`; leave `seat_zone` blank for unmatched rows. The JSON summary must contain `matched_count`, `matched_amount_cents`, `unmatched_count`, and `unmatched_amount_cents` as non-negative integers, with refund amounts counted as positive cents.
