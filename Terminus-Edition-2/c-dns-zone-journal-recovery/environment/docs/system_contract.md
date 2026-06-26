# Atlas DNS Journal Contract

Atlas is the internal authoritative-DNS publication service for payment and identity endpoints. A state directory contains:

- `manifest`: `generation<TAB>snapshot-file`
- the active `snapshot.N.tsv`
- `journal.log`, containing zero or more transactions

A snapshot begins with `GEN<TAB>N` and `SERIAL<TAB>U32`. It then contains `TX<TAB>transaction-id<TAB>change-digest` rows and `RR<TAB>name<TAB>type<TAB>ttl<TAB>value` rows. Unknown files in the state directory are not authoritative.

Journal transactions use `B|txid|base-serial|next-serial|change-digest`, one or more `O|...` operation rows, and `C|txid|checksum`. The checksum is the lowercase 16-digit FNV-1a-64 of the exact `B` and `O` rows including their newline delimiters. A transaction is committed only when its closing row is complete, its identifiers agree, and the checksum validates.

`zonectl recover --state DIR --out FILE` must materialize the authoritative state atomically, clear only journal bytes that were safely consumed, and write the JSON report. A final interrupted transaction is not committed. Corruption before the final interrupted transaction is an operator-visible failure and must not alter the active snapshot or journal.

`zonectl apply --state DIR --txid ID --changes FILE` accepts tab-separated `SET name type ttl value` and `DEL name type` rows. A successful new transaction advances the SOA serial by exactly one modulo 2^32.

`zonectl query --state DIR --out FILE` reports the active state without applying journal data.
