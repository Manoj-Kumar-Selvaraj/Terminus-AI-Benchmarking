# Endpoint design notes

Gateway endpoints:

- `s3` and `dynamodb` are gateway VPC endpoints.
- Both gateway endpoints must attach to every private route table: `rtb-private-a` and `rtb-private-b`.
- They must not attach to public route tables.
- NAT default routes are not a substitute for gateway endpoint route-table coverage.

Interface endpoints:

- Required interface endpoints are `ssm`, `ssmmessages`, and `ec2messages`.
- Interface endpoints must be placed only in private subnets.
- Private DNS must be enabled for all required SSM-family endpoints.
- The shared endpoint security group may allow TCP/443 from documented application sources only: `sg-app-staging`, `sg-batch-staging`, `10.42.16.0/20`, and `10.42.32.0/20`.
- `0.0.0.0/0` and `::/0` are never acceptable ingress sources for the endpoint security group.

Manifest schema for `endpoint_security_group_rules` in `security_groups.tf`:

- Each ingress rule uses `protocol`, `from_port`, `to_port`, `cidr_blocks`, `ipv6_cidr_blocks`, and `source_security_group_ids`.
- Security-group sources must use the plural list key `source_security_group_ids`, not `security_groups`, `security_group_ids`, or `source_security_group_id`.
- Every ingress rule must name at least one approved source via `cidr_blocks`, `ipv6_cidr_blocks`, or `source_security_group_ids`.
