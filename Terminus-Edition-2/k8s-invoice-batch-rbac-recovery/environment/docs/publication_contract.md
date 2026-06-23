# Publication Contract

Ledger artifacts are Secrets named `ledger-{window_id}` in `billing-batch`.

Publication rules:

- A billing window may produce at most one ledger artifact per nightly cycle.
- If a prior batch run for the same window is still active when the next schedule fires, the platform must not publish a second artifact for that window.
- The CronJob must enforce single-flight behavior for overlapping schedule slots.

The overlap fixture in `/app/sim/config.json` models a long-running first job and a second scheduled trigger before the first completes.
