The infrastructure state drift adjudicator rejects scans when live state uses abbreviated module labels. Fix `/app/src/drift_batch.pli`, `/app/src/drift_rules.pli`, or the batch harness so `/app/data/observed.psv` reconciles against `/app/data/ideal.psv`.

Milestone 2 keeps milestone 1 matching and consumption rules and enables `ALIAS_*` normalization from `/app/src/drift_rules.pli` (`raw=>canonical`, case-insensitive on compare keys). Matching compares canonical values; emit canonical `module_name` on `ALIGNED` rows only.

Status must be exactly `ALIGNED` or `DRIFTED`.
