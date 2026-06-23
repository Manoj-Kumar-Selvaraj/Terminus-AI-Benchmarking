The canonical payload semantic matcher still rejects checks where producers send abbreviated segment codes. Fix `/app/src/semantic_batch.pli`, `/app/src/semantic_rules.pli`, or the batch harness so `/app/data/actual.psv` reconciles against `/app/data/expected.psv`.

Milestone 2 keeps milestone 1 matching and consumption rules and enables `ALIAS_*` normalization from `/app/src/semantic_rules.pli` (`raw=>canonical`, case-insensitive on compare keys). Matching compares canonical values; emit canonical `segment_id` on `EQUAL` rows only.

Status must be exactly `EQUAL` or `DIFFER`.
