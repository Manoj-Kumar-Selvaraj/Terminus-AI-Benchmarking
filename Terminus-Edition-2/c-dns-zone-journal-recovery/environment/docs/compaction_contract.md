# Snapshot Generation Contract

The manifest is the authority for the active snapshot generation. A higher-numbered snapshot that is not named by the manifest is an orphan, not a candidate for automatic promotion.

Compaction writes a complete next-generation snapshot before atomically replacing the manifest. On restart:

- a crash before manifest replacement leaves the old generation active;
- a crash after manifest replacement leaves the new generation active;
- orphan temporary or final snapshots may be removed only after the manifest-selected snapshot has been validated;
- repeated compaction with no new journal work must preserve DNS contents, transaction history, and serial.

SOA serial succession follows unsigned 32-bit modulo arithmetic. `4294967295` is immediately followed by `0`.
