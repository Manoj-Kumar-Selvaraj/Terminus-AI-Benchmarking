# Matching rules

An adjustment row matches a pledge row when all of the following hold:

1. `pledge_id` values are identical full strings (not shared prefixes).
2. `donor_id` and `amount_cents` match after trimming surrounding spaces.
3. The pledge `status` is `BOOKED` (case-insensitive).
4. The adjustment `fund` is enabled in `config/methods.csv` and equals the pledge `fund` after normalization.
5. The fund is enabled in `config/methods.csv` and any configured donor/fund cap in `config/donor_limits.csv` is satisfied.
6. Each pledge input row may be consumed at most once; duplicate adjustments compete for the same pledge in file order.

Matched report rows use columns `pledge_id,donor_id,fund,amount_cents,status`. Emit canonical fund codes on matches and leave `fund` blank on unmatched rows. Summary amounts are positive integer cents.


Matched report rows must emit canonical uppercase fund values (`GENERAL`, `CAPITAL`, or `RELIEF`); unmatched report rows leave `fund` blank.
