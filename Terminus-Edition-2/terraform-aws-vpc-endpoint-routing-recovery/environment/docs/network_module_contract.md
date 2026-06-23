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
- Legacy output names and shapes are a supported API for downstream stacks. New aggregate outputs may be added but cannot replace the old names.
- The `module_output_contract` jsondecode local in `outputs.tf` is the inspector's source of truth for legacy outputs. It must be a flat map keyed by output name where each entry has `shape` and `value` keys. Legacy names are listed in `/app/fixtures/expected_outputs.json`.
- Resource identity must be preserved by stable keys or explicit migration metadata.
- `/app/docs/migration_constraints.md` must contain a completed release note of at least 50 words and 3 sentences covering legacy outputs, `moved` metadata, and non-destructive preservation of VPC, subnet, route table, and endpoint security group identities.

Do not make this recovery by editing evidence or fixture files, deleting network
resources, changing CIDRs, renaming environments, opening security groups to the
public internet, or replacing the module with a fake output-only module.
