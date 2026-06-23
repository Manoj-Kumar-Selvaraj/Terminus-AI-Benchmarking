# Matching rules

A refund matches a booking row when all of the following hold:

1. `booking_id` values are identical full strings (prefix-only matches are invalid).
2. `patron_id` and `amount_cents` match after trimming surrounding spaces.
3. Booking `status` is `TICKETED` (case-insensitive).
4. Refund `seat_zone` is enabled in `config/methods.csv` and equals the booking `seat_zone` after normalization (two different allowed zones never match).
5. Each booking input row may be consumed at most once.

Report columns: `booking_id,patron_id,seat_zone,amount_cents,status` in refund input order. Emit canonical `seat_zone` on matches; leave it blank when unmatched. Summary amounts are positive integer cents.
