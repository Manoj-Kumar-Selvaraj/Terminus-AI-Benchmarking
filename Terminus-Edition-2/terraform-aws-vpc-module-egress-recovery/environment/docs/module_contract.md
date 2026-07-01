# VPC module contract

Offline simulator only. Preserve `/app/infra/modules/vpc`, resource labels in `main.tf`, output keys in `outputs.tf`, and `/app/bin/vpcsim` subcommands `plan`, `apply`, and `validate` with flags `--config`, `--prior-state`, `--out`, and `--state`. Repair logic in `module.go`; rebuild with `go build -o /app/bin/vpcsim /app/cmd/vpcsim` after edits.

The hard recovery workflow is implemented through `/app/bin/vpc-recover`, built from `/app/cmd/vpcrecover/main.go`. Milestone verification uses `vpc-recover` because the incident requires correlating desired config, observed inventories, imported Terraform state, NAT health, audit inventory, and noisy production logs.

## Routing and subnet outputs

- App subnets use same-AZ NAT gateways for `0.0.0.0/0` routes.
- Data subnets remain isolated with no default internet route.
- App AZs without a same-AZ healthy NAT gateway must fail validation with `missing nat gateway` in the error.
- Outputs must include `vpc_id`, `public_subnet_ids`, `private_app_subnet_ids`, `isolated_data_subnet_ids`, `private_app_route_table_ids`, and `isolated_data_route_table_ids`.
- Recovery state must include `outputs.private_app_route_table_ids` from Milestone 2 onward. The value must match recovered app-tier route table IDs and must drive gateway endpoint associations.
- Subnet tags must include `Name` and `Tier`.

## Gateway endpoints

- Only S3 and DynamoDB gateway endpoints are supported.
- Gateway endpoint reconciliation follows endpoint service names, not config order.
- S3 and DynamoDB gateway endpoints attach only to private app route tables.
- Each endpoint's `route_table_ids` must be unique and must equal `outputs.private_app_route_table_ids`.
- Unsupported gateway endpoint services fail before mutation with `unsupported` in the error.
- Existing endpoint IDs, policies, tags, metadata, and policy account provenance must be preserved when safe.
- Endpoint policies retain tag `ManagedBy: terraform-aws-vpc-module` and use a nested IAM policy document. The verifier reads `policy.Statement[0].Condition.StringEquals["aws:PrincipalAccount"]`, so that path must exist and equal the configured workload/account contract.
- Endpoint policy account mismatch must fail before mutation with `account mismatch` in the error.

## CIDR validation and subnet identity

- Overlapping subnet CIDRs fail with `overlaps` in the error, including exact, containing, contained, and partial range overlaps.
- Subnets outside the VPC CIDR fail with `outside vpc_cidr` in the error.
- Ambiguous imported-state matches for the same CIDR fail with `ambiguous imported cidr`.
- Imported legacy subnet resources must be matched by CIDR, including addresses such as `module.vpc.aws_subnet.private[0]`.
- Prior-state or imported legacy subnet objects may omit `az`, so CIDR is the identity match for legacy moves.
- Imported subnet IDs and imported route table IDs must be preserved when a configured subnet CIDR matches imported state.
- Recovered subnet objects must keep evidence-derived `address`, `id`, `cidr`, `tier`, `az`, and `route_table_id` fields.
- Appending AZs must preserve existing subnet IDs by comparing unchanged CIDRs from prior/imported state and must not trigger destructive `replace` plan actions for unchanged resources.

## Imported state and moved resources

Legacy paths such as integer-indexed `module.vpc.aws_subnet.private[0]`, `[1]`, and `[2]` must be represented as moved actions to the matching current app subnet address for the same CIDR.

Recovered state must emit these moved entries under the top-level `moved` array. Do not place them only in `plan_actions`.

Each moved object uses this shape:

```json
{"action": "moved", "from": "<legacy address>", "to": "<current app subnet address>"}
```

Each legacy `from` address must appear at most once in `moved`. Repeated apply must not duplicate moved actions.

## Audit logging and resolver security

- Flow logs must cover every recovered subnet.
- Flow logs expose covered subnets under `flow_log.subnet_ids` as subnet ID strings.
- When the configured flow-log destination account matches the VPC account, recovery must preserve the existing flow-log ID and audit metadata from observed audit evidence.
- Flow-log destination account mismatch must fail before mutation with `account mismatch` in the error.
- Flow-log IAM policy must be a flat simulator object shaped as `{"Action": [...], "Resource": "<arn>"}`.
- The flow-log IAM policy must include a non-empty `Action` list, must not include `logs:*`, and every action must start with `logs:`.
- The flow-log IAM policy must include at least `logs:CreateLogStream` and `logs:PutLogEvents`.
- The flow-log IAM policy `Resource` must be a non-wildcard CloudWatch Logs ARN for the configured account and log group. It must include `log-group:` and end with `:*`.
- Resolver security group ingress is exactly two rules: TCP 53 and UDP 53 from configured corporate CIDRs only.
- Each resolver ingress rule must expose those CIDRs under the key `cidr_blocks`.
- Manual resolver rules from observed audit evidence must be reported in `drift_report` as `report_only` entries, not silently deleted. Preserve the observed manual rule details under the drift entry.

## vpcsim and recovery output schema

Key fields used by verifiers: `route_tables`, `subnets`, `gateway_endpoints`, `flow_log`, `resolver_security_group`, `drift_report`, `outputs`, `moved`, and `plan_actions`.

Flow log shape:

```json
{
  "id": "fl-...",
  "traffic_type": "ALL",
  "destination": "...",
  "metadata": {},
  "iam_policy": {"Action": ["..."], "Resource": "..."},
  "log_format": "... ${interface-id} ...",
  "subnet_ids": ["subnet-..."]
}
```

Resolver security group ingress rule shape:

```json
{"protocol": "tcp", "from_port": 53, "to_port": 53, "cidr_blocks": ["10.0.0.0/8"]}
```

Manual resolver drift shape:

```json
{
  "action": "report_only",
  "resource": "resolver_security_group",
  "observed": {
    "owner": "manual",
    "protocol": "tcp",
    "from_port": 853,
    "to_port": 853,
    "cidr_blocks": ["10.0.0.0/8"]
  }
}
```

The controller must never solve the incident by overwriting one static final JSON fixture. It must preserve unknown metadata, support dynamic account/AZ/NAT/CIDR/service-order changes, write atomic recovered state, and use `/app/state/recovery_journal.jsonl` for owner fencing and replay.