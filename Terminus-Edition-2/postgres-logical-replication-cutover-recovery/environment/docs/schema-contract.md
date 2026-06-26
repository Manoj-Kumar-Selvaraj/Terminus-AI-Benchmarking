# Schema compatibility contract

Source schema version 3 is the cutover contract. Explicit SQL `NULL` remains `NULL`; a target default is used only for an omitted column, never for a replicated null. Compatible character widening is allowed, narrowing and silent truncation are not. `SUSPENDED_LEGACY` may be translated to `SUSPENDED`; no other undocumented status translation is permitted.

Foreign-key visibility is transaction scoped. `profile_audit` is append-only. A schema-version mismatch, unknown enum, immutable-audit mutation, length violation, or failed dependent operation rejects the complete transaction and blocks cutover eligibility.
