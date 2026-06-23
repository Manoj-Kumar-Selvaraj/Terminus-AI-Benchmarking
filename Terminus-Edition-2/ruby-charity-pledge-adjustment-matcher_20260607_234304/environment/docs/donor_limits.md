# Donor limits

Milestone 5 adds `/app/config/donor_limits.csv` with columns:

```
donor_id,fund,max_adjustment_cents,enabled
```

A candidate pledge is donor-policy eligible only when a row matches the trimmed `donor_id`, the row fund normalizes to the same canonical fund as the candidate pledge, `enabled` is `true` case-insensitively after trimming, and the adjustment amount is less than or equal to `max_adjustment_cents`.

Fund names in this file use the same alias normalization as pledge and adjustment rows (`GEN`, `CAP`, `REL`). Blank donor ids, blank fund names, unsupported funds, missing enabled values, disabled rows, missing or non-integer maximum amounts, negative maximum amounts, and short malformed data rows are ineligible and should not crash the batch. When multiple well-formed rows normalize to the same donor and fund, the last such row in file order is authoritative.


The `enabled` field is trimmed and compared case-insensitively, so values such as `TRUE`, `True`, and ` true ` enable a well-formed donor/fund policy row. Donor ids are trimmed before matching.
