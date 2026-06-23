# PL/I Rule Deck Reference

`/app/src/tape_rules.pli` declares runtime policy constants read by the gawk harness:

| Declaration | Purpose |
|-------------|---------|
| `ELIGIBLE_STATE` | Catalog `state` required for verification |
| `OPEN_MOUNT_STATE` | Mount window state gate (milestone 3) |
| `REASON_1`–`REASON_3` | Allowed audit `verdict_code` values |
| `ALIAS_1`–`ALIAS_3` | `raw=>canonical` alias mappings (milestone 2) |

`/app/src/tape_batch.pli` `%SET` switches control matching mode: `KEY_COMPARE`, `CONSUME`, `ALIAS_MODE`, `WINDOW_MODE`.
