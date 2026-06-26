Authorization decisions now match policy, but retry traffic after a controller crash creates multiple capability serials for one upstream assertion. The same client operation may be retried after any local phase or after a response is lost. Review `/app/evidence/replay-restart.log` and `/app/docs/replay-contract.md` and repair the real exchange workflow.

Preserve one-time assertion ownership, exact idempotent responses, monotonic serial allocation, checksum journals, and process-safe state.

## Success criteria

1. The first valid exchange verifies the incoming SWA1 assertion against audience `profile-export`, then mints exactly one independently verifiable capability token for the requested downstream audience tied to the assertion `jti`.
2. Retrying the same `operation_id` and semantic request returns the **exact same token**.
3. Rebinding an `operation_id` to different scopes, or reusing a `jti` under another operation, fails closed.
4. Concurrent exchange processes converge on one minted token and one consumed serial.
5. Serial allocation is monotonic starting at **1001** and incrementing by **1** per mint (`next_serial` advances accordingly).
6. Injected failures after reservation, mint, or commit resume the same operation without duplicate serials or tokens. Call `maybe_fail` at the exact points documented in `/app/docs/replay-contract.md`: `AFTER_REPLAY_RESERVE`, `AFTER_TOKEN_MINT`, and `AFTER_EXCHANGE_COMMIT`. After `AFTER_TOKEN_MINT`, `/app/state/replay.json` must already contain the minted token and serial for that operation.
7. `broker recover` reconstructs replay state from the checksum journal, tolerating only a torn final line; interior content drift blocks recovery even if the changed line remains valid JSON. Journal `phase` values are `RESERVED`, `MINTED`, and `COMMITTED`, and complete journal records include a checksum field.

Restarts must tolerate only a torn final journal record. Do not modify `/opt/task-tools`.
