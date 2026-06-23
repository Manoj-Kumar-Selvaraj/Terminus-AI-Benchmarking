# Donor limits

Donor policy caps are loaded from `/app/config/donor_limits.csv` with columns:

```
donor_id,fund,max_adjustment_cents,enabled
```

Trim fields. Fund names use the same alias normalization as pledge and adjustment rows (`GEN`, `CAP`, `REL`).

## Well-formed rows

A row is **well-formed** when it has:

- a nonblank trimmed `donor_id`
- a fund that normalizes to an allowed canonical fund
- a parseable non-negative integer `max_adjustment_cents`
- a present `enabled` token (compared case-insensitively after trimming)

Blank donor ids, blank fund names, unsupported funds, missing enabled values, missing or non-integer maximum amounts, negative maximum amounts, and short malformed data rows are **not** well-formed and should not crash the batch.

The `enabled` flag affects match eligibility at query time. It does **not** make an otherwise well-formed row invalid for last-row-wins storage.

## Last row wins

When multiple **well-formed** rows normalize to the same `(donor_id, canonical fund)` key, the **last** such row in file order is authoritative — even when that row has `enabled=false`. Load every well-formed row into the lookup while parsing; do not skip disabled rows during load.

## Match eligibility

A candidate pledge is donor-policy eligible only when the authoritative row for its trimmed `donor_id` and canonical fund has `enabled=true` and the adjustment amount is less than or equal to `max_adjustment_cents`. If the authoritative row is disabled, matching is blocked even when an earlier enabled row existed for the same key.
