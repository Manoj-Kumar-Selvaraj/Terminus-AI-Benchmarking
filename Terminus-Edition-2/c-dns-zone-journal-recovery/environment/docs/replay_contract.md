# Transaction Replay Contract

Transaction IDs are durable operation identities, not log-row identities.

- Re-observing an already committed ID with the same change digest is a successful no-op.
- Reusing a committed ID for different changes is a conflict and must fail closed; the command must include the word `conflict` in stderr so operators can distinguish this from serial-chain or checksum failures.
- For a new ID, the transaction base serial must equal the current serial and the next serial must be its modulo-2^32 successor.
- Recovery must be restart-safe: applying the same committed journal bytes more than once cannot advance the serial twice or duplicate records.
- Record identity is `(name, type)`. `SET` replaces that record; `DEL` of an absent record is allowed.
