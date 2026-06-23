# Tape Alias Rules

When `ALIAS_MODE` is `ON` in `/app/src/tape_batch.pli`, the harness reads `ALIAS_*` declarations from `/app/src/tape_rules.pli`.

Each alias entry uses `raw=>canonical` form. Alias keys are trimmed and case-folded before lookup. Apply normalization on **both catalog and audit sides** before comparing `block_no` and `reel_id`.

Matching compares canonical values. Emit canonical `block_no` on `VERIFIED` rows only. Unknown alias codes remain unmatched.
