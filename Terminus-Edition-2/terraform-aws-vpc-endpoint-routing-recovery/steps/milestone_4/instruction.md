You are recovering the shared staging AWS networking Terraform module under `/app/modules/network`. This is an offline incident exercise: do not use AWS credentials, do not fetch providers from the internet, and do not edit verifier tests, evidence, or fixture files to hide the incident.

Use the operator evidence in `/app/evidence`, the contract docs in `/app/docs`, the staging and consumer fixtures under `/app/stacks`, and saved state fixtures under `/app/fixtures`. The local inspector `/app/scripts/inspect_network_contract.py` reads the Terraform module HCL and its `jsondecode` manifest locals to produce a semantic graph for offline validation.

Preserve the existing VPC CIDR, subnet CIDRs, public/private subnet classification, `staging` environment name, stable network resource identities, public CLI/file layout, and downstream output compatibility. Do not replace the module with a fake output-only module and do not solve by editing generated fixture/evidence files.

## Backward-compatible non-destructive migration

Downstream stacks still fail because old module output names changed during the refactor. The saved migration review also shows replacement risk for stable network resources whose identities should be preserved.

Complete the recovery so that:

- old output names and shapes used by the app-consumer fixture remain available;
- new outputs may remain, but they must not remove or change the old compatibility contract;
- downstream consumer fixtures resolve the expected VPC, subnet, route-table, endpoint, and security group IDs without code changes;
- stable VPC, subnet, route-table, NAT gateway, endpoint, and endpoint security group identities are preserved;
- resource address changes are covered by explicit Terraform `moved` blocks or an equivalent offline migration map;
- CIDR allocation and the `staging` environment name remain unchanged;
- `/app/docs/migration_constraints.md` contains a completed release note of at least 50 words and 3 sentences explaining the compatibility path and non-destructive migration approach; mention legacy outputs, `moved` metadata, and non-destructive preservation of VPC, subnet, route table, and endpoint security group identities, and replace the pending placeholder status.

## Module output contract manifest

The inspector validates `module_output_contract` in `/app/modules/network/outputs.tf`, not only Terraform `output` blocks. See `/app/docs/network_module_contract.md` for the full schema, per-output `shape` values, and example manifest.

Update that `jsondecode` local to a flat map keyed by output name where each entry has `shape` and `value` keys. Restore every legacy output name listed in `/app/fixtures/expected_outputs.json` with the correct semantic IDs in each entry's `value` field.

The aggregate outputs `network` and `endpoint_ids` **must remain** in `module_output_contract` and as Terraform `output` blocks alongside all legacy names. They are required compatibility outputs, not optional replacements.

Keep all prior route, endpoint, security, and DNS behavior intact.
