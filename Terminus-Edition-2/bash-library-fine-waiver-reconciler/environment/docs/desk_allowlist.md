# Desk Allowlist

Allowed match desks are loaded from `/app/config/channels.csv`:

```text
desk,enabled
FRONT,true
ONLINE,true
MOBILE,true
KIOSK,false
OTHER,false
```

A desk is allowed only when `enabled` is `true` (case-insensitive). Canonicalize values before checking the allowlist.

## Aliases

Waiver and fine desk fields may use legacy aliases:

| Alias | Canonical |
|-------|-----------|
| FR    | FRONT     |
| WEB   | ONLINE    |
| APP   | MOBILE    |
| KSK   | FRONT     |

Matched report rows must emit the canonical uppercase desk.
