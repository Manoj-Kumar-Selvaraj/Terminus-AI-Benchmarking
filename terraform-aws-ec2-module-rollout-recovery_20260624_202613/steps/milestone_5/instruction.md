# Reconcile imported state, hardening, journal damage, and manual drift

Service recovery exposed four remaining problems: legacy imports proposed destructive replacement, a torn final journal write blocked restart, manual instance drift was scheduled for repair instead of audit, and the instance profile still allowed unsafe metadata and broad permissions.

Preserve milestones 1–4. Use `/app/docs/recovery_contract.md`, `/app/docs/module_contract.md`, `/app/evidence/import_plan_excerpt.txt`, `/app/evidence/security_review.json`, and `/app/evidence/torn_rollout_journal.jsonl`.

## Required behavior

- Require IMDSv2 with the documented endpoint and hop limit.
- Render the exact least-privilege IAM statement Sids, actions, resources, and restrictive conditions documented in `/app/docs/recovery_contract.md`; wildcard actions are forbidden.
- Declare every documented legacy Terraform move in `state_migrations.tf`.
- Recover missing stable slots from legacy `Slot` tags and preserve imported instance IDs when release and capacity are unchanged.
- Unchanged imported state has no destructive or rolling replacement actions.
- Missing or invalid legacy slot provenance fails closed.
- Report launch-template, public-IP, subnet, and security-group drift independently as `report_only` using the exact drift entry schema in `/app/docs/recovery_contract.md`, preserving actual instance state.
- Truncate only an invalid final JSONL journal record while preserving all valid records; invalid interior corruption fails closed.
- Resume fenced in-progress rollout state idempotently after restart.
- Preserve public Terraform labels, outputs, and all earlier recovery behavior.

Do not add hidden feature toggles, fabricate trusted state, erase history, auto-repair report-only drift, persist credentials, or replace imported resources to avoid migration handling.
