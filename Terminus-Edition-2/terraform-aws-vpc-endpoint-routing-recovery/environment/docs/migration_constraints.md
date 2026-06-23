# Migration constraints

The refactor moved several module internals from list-indexed resource identity
to named identity. The migration must be non-destructive for stable network
resources. Existing VPCs, subnets, route tables, NAT gateways, gateway endpoints,
interface endpoints, and endpoint security groups must not be replaced.

Downstream stacks still consume these legacy output names:

- `vpc_id`
- `vpc_cidr_block`
- `private_subnet_ids`
- `public_subnet_ids`
- `private_route_table_ids`
- `public_route_table_ids`
- `gateway_vpc_endpoint_ids`
- `interface_vpc_endpoint_ids`
- `endpoint_security_group_id`
- `endpoint_security_group_ids`

The release note in this file should describe how the refactor preserves old
outputs while permitting new outputs. It should also mention the identity
migration path for resources whose address changed.

Current release status: pending; saved plan still requires review before the
staging stack can be promoted.
