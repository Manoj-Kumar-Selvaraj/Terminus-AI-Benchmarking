# One-time exchange and recovery contract

`operation_id` identifies a client exchange attempt; assertion `jti` identifies the one-time upstream credential. The exchange request audience is the downstream capability audience, normally `profile-export-api`, but the incoming SWA1 assertion itself must still verify against assertion audience `profile-export`. The first valid exchange may mint exactly one capability serial. Retrying the same operation and same semantic request returns the exact committed token. Reusing an operation ID for different content, or a JTI under another operation, fails closed.

Reservation, mint, and commit are durable phases. The controller may be killed after any phase. A restart reconstructs operation ownership and serial allocation from the checksum journal, tolerating only a torn final line. Concurrent processes must converge through the controller lock. A lost response after commit is an idempotent retry, not a second mint.

After the `MINTED` journal append, `/app/state/replay.json` must already record the allocated token and serial for that `operation_id` (status `MINTED`) before the `COMMITTED` phase runs. Crash injection at `AFTER_TOKEN_MINT` must therefore be recoverable from `replay.json` alone without replaying the mint.

## Exchange journal schema

Append-only `/app/state/exchange-journal.jsonl` records use `kind: "exchange"` and `phase` values:

- `RESERVED` — operation and assertion ownership recorded before mint
- `MINTED` — capability token and serial allocated
- `COMMITTED` — durable commit completed

Recovery replays these phases into `/app/state/replay.json`. Each complete journal record must carry a checksum over the canonical record content. Interior checksum corruption must fail closed even when the tampered line remains valid JSON and uses a valid phase; only a torn final line may be ignored.

## Injected failure points

`/opt/task-tools/capability-lab inject-failure --point <NAME>` arms `/app/state/failure.json`. Broker exchange code must call `maybe_fail('<NAME>')` at the matching phase (injected failures exit **75**):

| Point | Phase |
|-------|--------|
| `AFTER_REPLAY_RESERVE` | immediately after the `RESERVED` journal append |
| `AFTER_TOKEN_MINT` | immediately after the `MINTED` journal append, before commit |
| `AFTER_EXCHANGE_COMMIT` | immediately after the `COMMITTED` journal append |

String names are case-sensitive and must match exactly.
