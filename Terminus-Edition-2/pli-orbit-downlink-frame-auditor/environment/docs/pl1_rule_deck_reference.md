# PL/I Rule Deck Reference

`/app/src/audit_rules.pli` declares runtime policy constants read by the batch harness:

| Declaration | Purpose |
|-------------|---------|
| `ELIGIBLE_STATE` | Catalog `state` required for acceptance |
| `OPEN_PASS_STATE` | Pass window state gate |
| `VERDICT_A`–`VERDICT_C` | Allowed audit `verdict_code` values |
| `ALIAS_*` | `raw=>canonical` alias mappings |

`/app/src/audit_batch.pli` `%SET` switches describe the intended operating mode: `KEY_COMPARE`, `CONSUME`, `ALIAS_MODE`, and `WINDOW_MODE`.

The values in the shipped sample deck are not stable; verifier fixtures may rewrite this file before invoking `/app/scripts/run_batch.sh`.
