The retail batch trailer reconciler fails claims when stores submit shorthand debit/credit flags. Fix `/app/src/trailer_batch.pli`, `/app/src/trailer_rules.pli`, or the batch harness so `/app/data/trailer_claims.psv` reconciles against `/app/data/batches.psv`.

Milestone 2 keeps milestone 1 matching and consumption rules and enables `ALIAS_*` normalization from `/app/src/trailer_rules.pli` (`raw=>canonical`, case-insensitive on compare keys). Matching compares canonical values; emit canonical `dc_flag` on `BALANCED` rows only.

Status must be exactly `BALANCED` or `REJECTED`.
