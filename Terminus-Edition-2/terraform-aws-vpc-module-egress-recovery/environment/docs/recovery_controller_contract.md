# VPC Recovery Controller Contract

The incident cannot be repaired by rendering a fresh VPC. Implement `/app/bin/vpc-recover` from `/app/cmd/vpcrecover/main.go`.

Supported commands:

```bash
vpc-recover inspect --root /app --json
vpc-recover plan --root /app --json
vpc-recover apply --root /app --owner OWNER [--fail-after STAGE]
vpc-recover resume --root /app --owner OWNER
vpc-recover verify --root /app --json
```

The controller must read desired configuration, observed route and endpoint evidence, audit evidence, imported Terraform state, NAT health evidence, and the noisy production log. Preserve unknown metadata, write durable state under `/app/state`, and be safe to rerun. Do not solve the task by overwriting one static final JSON fixture.

The production evidence is noisy by design. Logs contain unrelated retry, throttling, and inventory messages; recovery must use structured evidence files and not a single hardcoded log string.

## Command output schema

All JSON command output uses snake_case keys.

`inspect --json` must include:

- `feature_level`: integer.
- `evidence_files`: array of evidence filenames, including `observed_routes.json`.

`plan --json` must be read-only and must not create, delete, or modify files under `/app/state`. Its output must include:

- `schema_version`: exactly `vpc-recovery.aws.1`.
- `environment`: the environment string from desired config.
- `config_digest`: a stable digest of the desired config and recovery inputs used for owner fencing.
- `route_tables`: the recovered route table objects.

`apply` and `resume` must write `/app/state/vpc_recovered_state.json` with at least:

- `schema_version`: exactly `vpc-recovery.aws.1`.
- `environment`.
- `config_digest`.
- `route_tables`.

Later milestones add `gateway_endpoints`, `subnets`, `moved`, `flow_log`, `resolver_security_group`, `drift_report`, `outputs`, and `plan_actions`. When present, these fields must preserve evidence-derived IDs, policies, metadata, imported-resource identities, and unknown fields described in the milestone instructions.

`outputs.private_app_route_table_ids` is required from gateway endpoint recovery onward. It must contain the recovered private app route table IDs and must be used as the gateway endpoint association source.

`verify --json` must read existing recovered state without mutation. Before a controller-generated recovered state exists, it must not report `phase: "READY"` or `valid: true`. After successful recovery, it must return `valid: true` and `phase: "READY"`.

## Journal and fencing

Journal records are JSONL objects in `/app/state/recovery_journal.jsonl` using snake_case keys. Every controller-written record must include:

- `event`: a string event name.
- `owner`: the recovery owner.
- `config_digest`: the digest for the operation when a desired config has been planned.

Milestone 1 writes `route_plan_written` before committing route recovery and `apply_committed` after recovered state is durable. Later milestones may add intermediate events such as endpoint commit events, but repeated successful `apply` must not append duplicate journal records for an already completed operation.

`--fail-after <stage>` simulates a crash or lost response after a durable stage commit. It must exit with a non-zero status, even if the recovered state or journal update was already written. Do not treat a fail-after as a successful command that only prints an interrupted JSON response.

Supported fail-after stages include:

- `route_commit`
- `endpoint_commit`

After a fail-after, `resume` by the same owner must continue safely without duplicating routes, endpoint associations, moved entries, or state-affecting journal records.

A torn final JSONL record may be truncated during `resume` and then recovery may continue. Corruption before the final record must fail closed with error substring `journal corruption`.

If a journal is active for a different owner, `resume` must fail with an error containing `stale owner`. If the desired config digest no longer matches the active journal, `resume` must fail with an error containing `config digest changed`.

Do not leave manual test artifacts in `/app/state` in the submitted environment. The verifier copies the initial environment into temporary incident roots, so stale journals or recovered state files in the starting image contaminate every test.

## Required fail-closed error substrings

Use these substrings in JSON `error` values for fail-closed cases:

- Missing same-AZ NAT: `missing nat gateway`.
- Unsupported gateway endpoint service: `unsupported`.
- Endpoint policy account mismatch: `account mismatch`.
- Flow-log destination account mismatch: `account mismatch`.
- CIDR overlap: `overlaps`.
- Subnet outside VPC CIDR: `outside vpc_cidr`.
- Ambiguous imported CIDR: `ambiguous imported cidr`.
- Middle journal corruption: `journal corruption`.
- Different resume owner: `stale owner`.
- Changed config on resume: `config digest changed`.