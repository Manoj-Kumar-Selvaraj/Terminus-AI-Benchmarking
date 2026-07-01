# Milestone 4 - Make alias cutover and Jenkins overlap safe

Partial batches now drain, but an in-flight execution mixes Lambda generations and the Jenkins comparison run creates a second archive after Lambda becomes primary. Use `/app/evidence/alias_cutover_trace.log`, `/app/docs/cutover-contract.md`, and `/app/docs/terraform-module-contract.md`.

Pin each execution to the generation active when it starts. `pipelinectl deploy --infra <directory>` must register the exact generation in that directory's `deployment.json`, never infer it from package hashes, aliases, or current runtime state. Cutover and rollback affect only new work; an in-flight execution keeps its original generation. Reconcile a lost alias response from committed runtime state. `cutover` and `rollback` return `active_generation`, `previous_generation`, `writer`, and the committed runtime `epoch`; rejected or undeployed generations exit nonzero.

When Lambda is primary, Jenkins remains read-only shadow work. Preserve rollback, generation-specific packages and aliases, and Jenkins comparison without allowing either path to create duplicate settlement effects.
