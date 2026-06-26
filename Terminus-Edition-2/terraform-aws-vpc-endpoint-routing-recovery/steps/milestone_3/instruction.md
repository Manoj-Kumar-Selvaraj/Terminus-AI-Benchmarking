You are recovering the shared staging AWS networking Terraform module under `/app/modules/network`. This is an offline incident exercise: do not use AWS credentials, do not fetch providers from the internet, and do not edit verifier tests, evidence, or fixture files to hide the incident.

Use the operator evidence in `/app/evidence`, the contract docs in `/app/docs`, the staging and consumer fixtures under `/app/stacks`, and saved state fixtures under `/app/fixtures`. The local inspector `/app/scripts/inspect_network_contract.py` reads the Terraform module HCL and its `jsondecode` manifest locals to produce a semantic graph for offline validation.

Preserve the existing VPC CIDR, subnet CIDRs, public/private subnet classification, `staging` environment name, stable network resource identities, public CLI/file layout, and downstream output compatibility. Do not replace the module with a fake output-only module and do not solve by editing generated fixture/evidence files.

## Interface endpoint security and DNS contract

Gateway endpoint routing is restored, but the security review still fails. The shared interface endpoint security group allows public ingress, and one SSM-family interface endpoint is placed where private workloads cannot use the expected private DNS behavior.

Recover the interface endpoint and security configuration so that:

- required interface endpoints are placed only in private subnets;
- private DNS remains enabled for required SSM-family interface endpoints;
- endpoint security group ingress permits TCP/443 only from the documented application security groups or private application CIDRs in `/app/fixtures/allowed_endpoint_sources.json`;
- endpoint security group ingress does not include `0.0.0.0/0`, `::/0`, or a broad allow-everything source;
- downstream app fixtures can still resolve the expected private endpoint IDs and security group ID;
- endpoint resources are preserved rather than deleted to silence the security finding.

## Manifest schema for endpoint security group rules

The offline inspector reads `endpoint_security_group_rules` in `/app/modules/network/security_groups.tf`. Each ingress rule must use these exact field names:

- `protocol`, `from_port`, `to_port`
- `cidr_blocks` (list) and `ipv6_cidr_blocks` (list) for CIDR sources
- `source_security_group_ids` (list) for security-group sources — use this plural key, not `security_groups`, `security_group_ids`, or `source_security_group_id`

Every ingress rule must name at least one approved source via `cidr_blocks`, `ipv6_cidr_blocks`, or `source_security_group_ids`. The inspector reads manifest JSON keys literally — see `/app/docs/network_module_contract.md` and `/app/docs/endpoint_design.md` for the full schema and worked ingress examples.

Keep the prior route-table and gateway endpoint fixes intact.
