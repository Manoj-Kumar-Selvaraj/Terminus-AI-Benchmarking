# Audit Alias Rules

When `ALIAS_MODE` is `ON` in `/app/src/audit_batch.pli`, the harness reads `ALIAS_*` declarations from `/app/src/audit_rules.pli`.

Each alias entry uses `raw=>canonical` form. Alias keys are trimmed and case-folded before lookup. Apply normalization on **both catalog and audit sides** before comparing `craft_id`, `channel`, and `service_class`.

Matching compares canonical values. Emit canonical `service_class` on `ACCEPTED` rows only.
