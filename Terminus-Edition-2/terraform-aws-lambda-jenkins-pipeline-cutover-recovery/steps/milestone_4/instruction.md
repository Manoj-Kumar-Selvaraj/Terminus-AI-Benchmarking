# Milestone 4 — Make alias cutover and Jenkins overlap safe

Partial batches now drain correctly. The staged rollout exposes a deeper cutover failure: one in-flight execution reports stages from two Lambda generations, and the Jenkins comparison run produces a second archive event after Lambda becomes primary.

Review:

- `/app/evidence/alias_cutover_trace.log`
- `/app/docs/cutover-contract.md`
- `/app/docs/terraform-module-contract.md`

Make deployment generation selection stable for the lifetime of an execution. Alias changes and rollback must affect only new work. A control-plane response may be lost after the alias change commits; the controller must reconcile the committed state instead of blindly reversing or duplicating the transition. `pipelinectl cutover` and `pipelinectl rollback` must return cutover JSON including `active_generation`, `previous_generation`, `writer`, and `epoch`, where `epoch` matches the trusted runtime after the transition commits.

During Lambda-primary operation, Jenkins remains an observation-only shadow. Preserve rollback capability and old-generation completion without allowing both systems to write. Keep Terraform package hashes and aliases version-specific; do not solve the incident by pinning all traffic permanently to one generation or by disabling the Jenkins comparison path.
