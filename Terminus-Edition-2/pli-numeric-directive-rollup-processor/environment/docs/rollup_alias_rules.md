# Rollup Alias Rules

When `ALIAS_MODE` is `ON` in `/app/src/rollup_batch.pli`, the harness reads `ALIAS_*` declarations from `/app/src/rollup_rules.pli`.

Each alias entry uses `raw=>canonical` form. Alias keys are trimmed and case-folded before lookup. Apply normalization on **both directive and accumulator sides** before comparing `base_radix` and `segment_id`.

Matching compares canonical values. Emit canonical `segment_id` on `ROLLED` rows only. Unknown alias codes remain unmatched.
