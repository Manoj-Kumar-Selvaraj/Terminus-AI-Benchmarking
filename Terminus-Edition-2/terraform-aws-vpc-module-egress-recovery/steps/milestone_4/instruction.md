# Restore audit-grade flow logs and resolver security boundaries

You are on the network platform rotation for a failed Terraform AWS VPC module rollout. This is offline: do not call AWS and do not require Terraform. Use `/app/bin/vpcsim`, `/app/docs/module_contract.md`, and `/app/evidence` to diagnose the incident. Repair logic in `/app/infra/modules/vpc/module.go` and rebuild with `go build -o /app/bin/vpcsim /app/cmd/vpcsim`.

## Requirements

- Emit VPC flow logs covering all subnets with `traffic_type: ALL` and the configured destination.
- The flow log object must list every subnet id under the key `subnet_ids` (not `resource_ids` or other aliases).
- Flow log IAM policy must be the simulator's flat shape `{"Action": [...], "Resource": "<arn>"}`, not a nested AWS policy document. `Action` must be a non-empty list. Its `Resource` must not be `*` and must include the configured `log_group_arn`.
- Flow log `log_format` must include `${interface-id}` so audit records identify the network interface.
- Flow log `id` must use the module `_id("fl", ...)` convention (prefix `fl-`).
- Resolver security group `id` must use the module `_id("sg", ...)` convention (prefix `sg-`).
- Resolver security group ingress must be exactly two rules: TCP 53 and UDP 53 from configured corporate CIDRs only (no `0.0.0.0/0`). Each ingress rule must expose corporate CIDRs under the key `cidr_blocks` (not `cidrs` or other aliases).
- Preserve `main.tf` resource labels and `outputs.tf` output keys.

Compatibility constraints: keep `/app/infra/modules/vpc`, all labels in `main.tf`, all outputs in `outputs.tf`, and CLI flags `plan`, `apply`, `validate`, `--config`, `--prior-state`, `--out`, `--state`. Do not hardcode sample JSON or edit verifier fixtures.
