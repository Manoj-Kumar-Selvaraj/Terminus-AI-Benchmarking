# Private egress module contract

The `private_egress` module under `/app/modules/private_egress` must model a production-style VPC with per-AZ public, app, and data subnets, same-AZ NAT coverage for app tiers, isolated data subnets, interface and gateway endpoints, and PrivateLink-safe policy shapes.

## Required Terraform resource names

| Resource | Name | Notes |
|----------|------|-------|
| Interface VPC endpoints | `aws_vpc_endpoint.interface` | `for_each` over the ten required interface services |
| Gateway VPC endpoints | `aws_vpc_endpoint.gateway` | `for_each` over `s3` and `dynamodb` |
| Endpoint security group | `aws_security_group.endpoint` | TCP 443 from workload CIDRs |
| Resolver security group | `aws_security_group.resolver` | TCP and UDP 53 from corporate DNS CIDRs |
| Subnet flow logs | `aws_flow_log.subnet` | Keys `public-<az>`, `app-<az>`, `data-<az>` |
| Flow-log delivery policy | `aws_iam_role_policy` | Inline role policy attached to the flow-log IAM role; policy must be visible as the resource `policy` value in plan JSON |
| Runtime queue | `aws_sqs_queue.runtime` | KMS-encrypted runtime queue |
| Queue policy | `aws_sqs_queue_policy.runtime` | Allow-through-endpoint plus explicit Deny controls |

PrivateLink policy documents must bind to the configured workload principal ARNs and artifact bucket/object ARNs. They must not use wildcard principals, wildcard actions, wildcard-only resources, broad IAM account wildcards, or literal region/account strings.

Interface endpoints use only app subnet IDs. S3 and DynamoDB gateway endpoints attach to app and data route tables through `route_table_ids` expressions that reference `aws_route_table.app` and `aws_route_table.data`, never public route tables. Endpoint security group ingress allows TCP 443 only from the app and data CIDRs in `var.azs`; for the greenfield fixture those are `10.42.11.0/24`, `10.42.12.0/24`, `10.42.13.0/24`, `10.42.21.0/24`, `10.42.22.0/24`, and `10.42.23.0/24`.

Subnet flow logs are keyed for every tier/AZ as `aws_flow_log.subnet["public-<az>"]`, `aws_flow_log.subnet["app-<az>"]`, and `aws_flow_log.subnet["data-<az>"]`. Each flow log uses a log format containing `${interface-id}` and `traffic_type = ALL`. Flow-log delivery permissions must be modeled as an inline `aws_iam_role_policy` attached to the flow-log IAM role, must scope CloudWatch log group ARNs, and must not use `Resource: "*"`. Construct the log-group ARN from input values such as `var.region`, `var.account_id`, and the name prefix so it is fully known in `terraform plan -refresh=false`.

Resolver ingress must be exactly two rules, TCP and UDP 53, sourced from the configured corporate DNS CIDRs. KMS key policies must not use wildcard actions such as `kms:*`.

The runtime queue policy must include explicit Deny statements that reference `aws:SecureTransport` and `aws:SourceVpce`, with endpoint fencing tied to `aws_vpc_endpoint.interface["sqs"]`.

Recovery is plan-only. Agents must prove convergence with `terraform validate`, `terraform plan -refresh=false`, and `terraform show -json` without live AWS reads.
