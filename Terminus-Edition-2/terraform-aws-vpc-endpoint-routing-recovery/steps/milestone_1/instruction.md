You are recovering the shared staging AWS networking Terraform module under `/app/modules/network`. This is an offline incident exercise: do not use AWS credentials, do not fetch providers from the internet, and do not edit verifier tests, evidence, or fixture files to hide the incident.

Use the operator evidence in `/app/evidence`, the contract docs in `/app/docs`, the staging and consumer fixtures under `/app/stacks`, and saved state fixtures under `/app/fixtures`. The local inspector `/app/scripts/inspect_network_contract.py` reads the Terraform module HCL and its `jsondecode` manifest locals to produce a semantic graph for offline validation.

Preserve the existing VPC CIDR, subnet CIDRs, public/private subnet classification, `staging` environment name, stable network resource identities, public CLI/file layout, and downstream output compatibility. Do not replace the module with a fake output-only module and do not solve by editing generated fixture/evidence files.

## Private route-table drift recovery

The saved staging plan and reachability report show private subnet route-table drift after the module refactor. Private workloads in one AZ no longer have the expected NAT egress path, and route-table association churn appears in the plan review.

Recover the module so that:

- private subnets remain associated with private route tables;
- public subnets remain associated with public route tables;
- every private route table keeps a NAT default route for `0.0.0.0/0`;
- public route tables do not receive private NAT routes;
- the existing VPC, subnets, route tables, NAT gateways, environment name, and CIDR allocation remain unchanged;
- no destructive replacement risk is introduced for stable network resources while making this recovery change.

The normal Terraform module files under `/app/modules/network` must remain the source of truth for the inspector; fixture and evidence files are read-only incident inputs.
