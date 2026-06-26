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

## Manifest schema for `endpoint_security_group_rules`

The offline inspector reads the `endpoint_security_group_rules` `jsondecode` local in `/app/modules/network/security_groups.tf` **verbatim**. It does not translate Terraform resource argument names. Use these exact JSON keys on every ingress rule:

- `protocol`, `from_port`, `to_port`
- `cidr_blocks` (list) and `ipv6_cidr_blocks` (list) for CIDR sources
- `source_security_group_ids` (list) for security-group sources

Security-group sources must use the plural list key `source_security_group_ids`. The inspector does **not** accept these aliases:

- `security_groups`
- `security_group_ids`
- `source_security_group_id`

Every ingress rule must name at least one approved source via `cidr_blocks`, `ipv6_cidr_blocks`, or `source_security_group_ids`. Include empty lists for keys you do not use.

### Worked ingress examples

Security-group rule (application workloads):

```json
{
  "description": "application workloads to shared interface endpoints",
  "protocol": "tcp",
  "from_port": 443,
  "to_port": 443,
  "source_security_group_ids": ["sg-app-staging", "sg-batch-staging"],
  "cidr_blocks": [],
  "ipv6_cidr_blocks": []
}
```

CIDR rule (private subnet fallback):

```json
{
  "description": "private subnet CIDR fallback for endpoint clients",
  "protocol": "tcp",
  "from_port": 443,
  "to_port": 443,
  "source_security_group_ids": [],
  "cidr_blocks": ["10.42.16.0/20", "10.42.32.0/20"],
  "ipv6_cidr_blocks": []
}
```

See also `/app/docs/network_module_contract.md` for the full module contract.
