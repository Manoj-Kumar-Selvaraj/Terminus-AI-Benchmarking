# Milestone 1 — Restore the Lambda deployment and stage handoff

The settlement operations team cut over the twelve-stage Jenkins job to Lambda during the maintenance window. Terraform reported a successful apply, but the runtime inventory does not match the Jenkins pipeline and the first production batch cannot complete the expected stage sequence.

Start with:

- `/app/evidence/incident_timeline.md`
- `/app/evidence/terraform_plan_excerpt.txt`
- `/app/evidence/jenkins_console_excerpt.log`
- `/app/docs/pipeline-contract.md`
- `/app/docs/terraform-module-contract.md`

Repair the Terraform-backed deployment and Go deployment loader so that the trusted offline runtime receives the complete ordered function fleet. Preserve the public CLI and existing valid stage names.

Success requires all twelve stages to be deployed in the documented order through the pinned Terraform AWS Lambda community module contract, with immutable published packages, versioned `live` aliases, stage-specific function identities, the exact documented per-stage resource settings, and the exact least-privilege action set for each stage. A normal batch must traverse the entire workflow without losing its execution, batch, item, or artifact identity.

Treat the deployment documents as a strict contract rather than a best-effort template. Reject a missing, duplicated, or reordered stage; a wrong module source or version; a legacy runtime; an unversioned alias; a shared function or package identity; any changed timeout, memory, concurrency, or permission set; and any wildcard action or principal. Rejection must occur before the trusted runtime records a deployment.

Do not replace the migration with one shared Lambda, invoke `$LATEST`, introduce wildcard permissions, edit the trusted runtime, or write runtime state directly.
