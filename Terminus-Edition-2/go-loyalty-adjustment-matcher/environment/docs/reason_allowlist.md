# Reason Allowlist

Allowed match reasons are loaded from `/app/config/reasons.csv`:

```text
reason,enabled
PURCHASE,true
BONUS,true
PROMO,true
CHECK,false
```

A reason is allowed only when `enabled` is `true` (case-insensitive). Canonicalize values before checking the allowlist.

## Aliases

Adjustment and accrual reason fields may use legacy aliases:

| Alias | Canonical |
|-------|-----------|
| BNS   | BONUS     |
| PRM   | PROMO     |
| PUR   | PURCHASE  |

Matched report rows must emit the canonical uppercase reason.
