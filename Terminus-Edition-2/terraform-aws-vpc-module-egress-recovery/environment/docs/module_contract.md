# VPC module contract

Offline simulator only. Preserve `/app/infra/modules/vpc`, resource labels in `main.tf`, output keys in `outputs.tf`, and `tools/vpcsim.py plan|apply|validate` CLI flags (`--config`, `--prior-state`, `--out`, `--state`).

## Routing (Milestone 1)

- App subnets use same-AZ NAT gateways for `0.0.0.0/0` routes.
- Data subnets remain isolated with no default internet route.
- Outputs must include: `vpc_id`, `public_subnet_ids`, `private_app_subnet_ids`, `isolated_data_subnet_ids`, `private_app_route_table_ids`, `isolated_data_route_table_ids`.
- Subnet tags must include `Name` and `Tier`.

## Gateway endpoints (Milestone 2)

- S3 and DynamoDB gateway endpoints attach only to app route tables.
- Unsupported gateway endpoint services fail validation with `unsupported` in the error.
- Endpoint policies retain account `111122223333` and tag `ManagedBy: terraform-aws-vpc-module`.

## CIDR validation (Milestone 3)

- Overlapping subnet CIDRs fail with `overlaps` in the error.
- Subnets outside the VPC CIDR fail with `outside vpc_cidr` in the error.
- Appending AZs must not trigger destructive `replace` plan actions.

## Audit logging and resolver (Milestone 4)

- Flow logs cover all subnets with `traffic_type: ALL`, configured destination, non-wildcard IAM `Resource`, and `${interface-id}` in `log_format`.
- Resolver security group has exactly two ingress rules: TCP 53 and UDP 53 from configured corporate CIDRs only.

## Imported state (Milestone 5)

- Unchanged imported state produces zero `replace` plan actions.
- Legacy paths like `module.vpc.aws_subnet.private` are represented as `moved` actions to app subnet addresses.
- App AZs without same-AZ NAT fail with `missing nat gateway` in the error.

## vpcsim plan output schema

Key fields used by verifiers: `route_tables`, `subnets`, `gateway_endpoints`, `flow_log`, `resolver_security_group`, `outputs`, `moved`, `plan_actions`.
