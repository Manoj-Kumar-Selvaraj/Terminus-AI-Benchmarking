# Shared network module contract

The `modules/network` Terraform module owns the staging shared VPC, public and
private subnets, route tables, default routes, NAT egress, S3/DynamoDB gateway
VPC endpoints, SSM-family interface endpoints, and the endpoint security group.
The verifier is offline: it reads Terraform HCL plus the `jsondecode` manifest
locals inside the module, saved state fixtures, and downstream consumer fixtures.
It must not contact AWS or require cloud credentials.

Compatibility constraints:

- Preserve the `staging` environment name.
- Preserve the VPC ID `vpc-staging-01` and CIDR `10.42.0.0/16`.
- Preserve the existing subnet IDs, subnet CIDRs, AZs, and public/private tier classification.
- Preserve the existing route table IDs and NAT gateway IDs.
- Private subnets must remain on private route tables, and public subnets must remain on public route tables.
- Private route tables must keep NAT default routes for internet egress.
- S3 and DynamoDB gateway endpoints are private route-table contracts only.
- Interface endpoints are private-subnet contracts and must keep private DNS where the endpoint design says so.
- Legacy output names and shapes are a supported API for downstream stacks. Required aggregate outputs must coexist with legacy names and cannot replace them.
- Resource identity must be preserved by stable keys or explicit migration metadata.
- `/app/docs/migration_constraints.md` must contain a completed release note of at least 50 words and 3 sentences covering legacy outputs, `moved` metadata, and non-destructive preservation of VPC, subnet, route table, and endpoint security group identities.

Do not make this recovery by editing evidence or fixture files, deleting network
resources, changing CIDRs, renaming environments, opening security groups to the
public internet, or replacing the module with a fake output-only module.

## `endpoint_security_group_rules` manifest

Location: `locals { endpoint_security_group_rules = jsondecode(<<JSON ...`)` in `/app/modules/network/security_groups.tf`.

The inspector parses this JSON manifest literally. It does not read `aws_security_group` resource blocks for ingress semantics.

Each ingress rule must include these exact keys:

- `protocol`, `from_port`, `to_port`
- `cidr_blocks` (list), `ipv6_cidr_blocks` (list)
- `source_security_group_ids` (list) — required key name even when empty

Do not use `security_groups`, `security_group_ids`, or `source_security_group_id`.

See `/app/docs/endpoint_design.md` for worked ingress examples and approved source lists.

## `module_output_contract` manifest

Location: `locals { module_output_contract = jsondecode(<<JSON ...`)` in `/app/modules/network/outputs.tf`.

The inspector validates this manifest, not only Terraform `output` blocks. Structure:

- Flat map keyed by output name
- Each entry: `{ "shape": "<type>", "value": <semantic-id-or-structure> }`

### Required legacy outputs

Restore every key listed in `/app/fixtures/expected_outputs.json` with the correct semantic `value`. Expected `shape` per output:

| Output name | shape |
|-------------|-------|
| `vpc_id` | `string` |
| `vpc_cidr_block` | `string` |
| `endpoint_security_group_id` | `string` |
| `private_subnet_ids` | `list(string)` |
| `public_subnet_ids` | `list(string)` |
| `private_route_table_ids` | `list(string)` |
| `public_route_table_ids` | `list(string)` |
| `endpoint_security_group_ids` | `list(string)` |
| `gateway_vpc_endpoint_ids` | `map(string)` |
| `interface_vpc_endpoint_ids` | `map(string)` |

### Required aggregate outputs

These outputs are **required** in both `module_output_contract` and Terraform `output` blocks. They must coexist with all legacy names above:

| Output name | shape | purpose |
|-------------|-------|---------|
| `network` | `object` | aggregate VPC, private subnet IDs, endpoint security group |
| `endpoint_ids` | `map(string)` | merged gateway + interface endpoint IDs |

### Example manifest excerpt

```json
{
  "vpc_id": {
    "shape": "string",
    "value": "vpc-staging-01"
  },
  "gateway_vpc_endpoint_ids": {
    "shape": "map(string)",
    "value": {
      "s3": "vpce-gw-s3",
      "dynamodb": "vpce-gw-dynamodb"
    }
  },
  "network": {
    "shape": "object",
    "value": {
      "vpc": "vpc-staging-01",
      "private_subnets": ["subnet-private-a", "subnet-private-b"],
      "endpoint_security_group": "sg-vpce-staging"
    }
  },
  "endpoint_ids": {
    "shape": "map(string)",
    "value": {
      "s3": "vpce-gw-s3",
      "dynamodb": "vpce-gw-dynamodb",
      "ssm": "vpce-if-ssm",
      "ssmmessages": "vpce-if-ssmmessages",
      "ec2messages": "vpce-if-ec2messages"
    }
  }
}
```

Each legacy output also needs a matching Terraform `output "<name>"` block. See `/app/docs/migration_constraints.md` for downstream compatibility notes.
