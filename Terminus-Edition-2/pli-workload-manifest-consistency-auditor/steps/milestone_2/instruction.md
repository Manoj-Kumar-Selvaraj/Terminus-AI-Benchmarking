The workload manifest consistency auditor fails checks when operators register shorthand port names. Fix `/app/src/manifest_batch.pli`, `/app/src/manifest_rules.pli`, or the batch harness so `/app/data/rollout_checks.psv` reconciles against `/app/data/manifests.psv`.

Milestone 2 keeps milestone 1 matching and consumption rules and enables `ALIAS_*` normalization from `/app/src/manifest_rules.pli` (`raw=>canonical`, case-insensitive on compare keys). Matching compares canonical values; emit canonical `port_name` on `CONSISTENT` rows only.

Status must be exactly `CONSISTENT` or `DRIFTED`.
