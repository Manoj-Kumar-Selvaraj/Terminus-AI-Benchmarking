# PL/I Rule Deck Reference

`/app/src/rollup_rules.pli` declares runtime policy constants read by the gawk harness:

| Declaration | Purpose |
|-------------|---------|
| `ELIGIBLE_STATE` | Directive `state` required for rollup |
| `OPEN_ROLLUP_STATE` | Rollup window state gate (milestone 3) |
| `REASON_1`–`REASON_3` | Allowed accumulator `opcode` values |
| `ALIAS_1`–`ALIAS_3` | `raw=>canonical` alias mappings (milestone 2) |

`/app/src/rollup_batch.pli` `%SET` switches control matching mode: `KEY_COMPARE`, `CONSUME`, `ALIAS_MODE`, `WINDOW_MODE`.
