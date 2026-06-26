At 02:14 UTC an Atlas DNS publisher lost power while writing an update. The surviving publisher continued serving traffic, but the restarted node refused to publish any state even though its last complete transactions were intact. Review `/app/evidence/incident_timeline.log`, `/app/evidence/startup_stderr.log`, `/app/docs/system_contract.md`, and the implementation under `/app/src`.

Restore journal recovery so that a final interrupted transaction is discarded without losing earlier committed updates. Recovery must validate complete transactions, fail closed on corruption that is not merely the interrupted tail, leave authoritative files unchanged after such a failure, and preserve the public `zonectl` commands and state formats.

The verifier exercises multiple committed transactions followed by different torn-tail shapes, checksum and identifier corruption, unchanged-state guarantees after rejection, deterministic record replacement/deletion, and restart-safe recovery reports.
