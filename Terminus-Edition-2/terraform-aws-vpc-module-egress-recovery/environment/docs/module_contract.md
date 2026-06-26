# VPC module contract

Offline simulator only. Preserve `/app/infra/modules/vpc`, resource labels in `main.tf`, output keys in `outputs.tf`, and `/app/bin/vpcsim` subcommands `plan`, `apply`, and `validate` with flags `--config`, `--prior-state`, `--out`, and `--state`. Repair logic in `module.go`; rebuild with `go build -o /app/bin/vpcsim /app/cmd/vpcsim` after edits.

## Routing and subnet outputs

- App subnets use same-AZ NAT gateways for `0.0.0.0/0` routes.
- Data subnets remain isolated with no default internet route.
- App AZs without a same-AZ NAT gateway must fail validation with `missing nat gateway` in the error.
- Outputs must include: `vpc_id`, `public_subnet_ids`, `private_app_subnet_ids`, `isolated_data_subnet_ids`, `private_app_route_table_ids`, `isolated_data_route_table_ids`.
- Subnet tags must include `Name` and `Tier`.

## Gateway endpoints

- S3 and DynamoDB gateway endpoints attach only to app route tables.
- Unsupported gateway endpoint services fail validation with `unsupported` in the error.
- Endpoint policies retain tag `ManagedBy: terraform-aws-vpc-module` and use a nested IAM policy document. The verifier reads `policy.Statement[0].Condition.StringEquals["aws:PrincipalAccount"]`, so that path must exist and equal `111122223333`.

## CIDR validation and subnet identity

- Overlapping subnet CIDRs fail with `overlaps` in the error, including partial range overlap rather than only identical strings.
- Subnets outside the VPC CIDR fail with `outside vpc_cidr` in the error.
- Appending AZs must preserve existing subnet IDs by comparing unchanged CIDRs from `--prior-state`, and must not trigger destructive `replace` plan actions.

## Audit logging and resolver security

- Flow logs cover all subnets with `traffic_type: ALL`, configured destination, `${interface-id}` in `log_format`, and a flat simulator IAM policy object shaped as `{"Action": [...], "Resource": "<arn>"}`. The policy must include a non-empty `Action` list, must not use a nested AWS `Statement` document, and its `Resource` value must be non-wildcard and include the configured `log_group_arn`.
- The flow log object must list covered subnets under the key `subnet_ids` (sorted subnet id strings).
- Flow log `id` values use the module `_id("fl", ...)` helper (prefix `fl-`).
- Resolver security group `id` values use the module `_id("sg", ...)` helper (prefix `sg-`).
- Resolver security group ingress is exactly two rules: TCP 53 and UDP 53 from configured corporate CIDRs only. Each ingress rule must expose those CIDRs under the key `cidr_blocks`.

## Imported state and moved resources

- Unchanged imported state produces zero `replace` plan actions.
- Legacy paths such as integer-indexed `module.vpc.aws_subnet.private[0]` are represented as moved actions to the matching app subnet address for the same CIDR. Prior-state legacy subnet objects may omit `az`, so match them by CIDR. Moved objects use `{"action": "moved", "from": "<legacy address>", "to": "<app address>"}`.
- Emit each legacy-subnet moved object once in the combined evidence set `moved + plan_actions`. The standard task shape is to put these moved objects in `plan_actions` and leave `moved` empty; do not duplicate the same `from` address in both arrays.

## vpcsim plan output schema

Key fields used by verifiers: `route_tables`, `subnets`, `gateway_endpoints`, `flow_log`, `resolver_security_group`, `outputs`, `moved`, `plan_actions`.

Flow log shape:

```json
{
  "id": "fl-...",
  "traffic_type": "ALL",
  "destination": "...",
  "iam_policy": {"Action": ["..."], "Resource": "..."},
  "log_format": "... ${interface-id} ...",
  "subnet_ids": ["subnet-..."]
}
```

Resolver security group ingress rule shape:

```json
{"protocol": "tcp", "from_port": 53, "to_port": 53, "cidr_blocks": ["10.0.0.0/8"]}
```
