# Migration constraints

The refactor moved several module internals from list-indexed resource identity
to named identity. The migration must be non-destructive for stable network
resources. Existing VPCs, subnets, route tables, NAT gateways, gateway endpoints,
interface endpoints, and endpoint security groups must not be replaced.

## Legacy output names

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

## Required aggregate outputs

The refactor introduced aggregate outputs that **must remain** alongside every legacy name above:

- `network` — aggregate object with VPC, private subnet IDs, and endpoint security group
- `endpoint_ids` — merged map of gateway and interface endpoint IDs

Both aggregates are required in `module_output_contract` and as Terraform `output` blocks. They do not replace legacy names.

## Output contract manifest format

The inspector reads `module_output_contract` in `/app/modules/network/outputs.tf`. Each output entry must use this shape:

```json
"<output_name>": {
  "shape": "<string|list(string)|map(string)|object>",
  "value": <semantic-id-matching-fixtures>
}
```

Full schema, per-output `shape` values, and a worked example are in `/app/docs/network_module_contract.md`. Semantic IDs must match `/app/fixtures/expected_outputs.json` for legacy outputs and satisfy `/app/stacks/app-consumer/expected_inputs.json` for downstream compatibility.

## Release note

The release note in this file should describe how the refactor preserves old
outputs while keeping the required `network` and `endpoint_ids` aggregates. It
should also mention the identity migration path for resources whose address changed.

Current release status: pending; saved plan still requires review before the
staging stack can be promoted.
