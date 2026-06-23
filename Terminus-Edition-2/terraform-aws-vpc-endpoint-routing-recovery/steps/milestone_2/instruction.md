You are recovering the shared staging AWS networking Terraform module under `/app/modules/network`. This is an offline incident exercise: do not use AWS credentials, do not fetch providers from the internet, and do not edit verifier tests, evidence, or fixture files to hide the incident.

Use the operator evidence in `/app/evidence`, the contract docs in `/app/docs`, the staging and consumer fixtures under `/app/stacks`, and saved state fixtures under `/app/fixtures`. The local inspector `/app/scripts/inspect_network_contract.py` reads the Terraform module HCL and its `jsondecode` manifest locals to produce a semantic graph for offline validation.

Preserve the existing VPC CIDR, subnet CIDRs, public/private subnet classification, `staging` environment name, stable network resource identities, public CLI/file layout, and downstream output compatibility. Do not replace the module with a fake output-only module and do not solve by editing generated fixture/evidence files.

## Gateway endpoint private routing recovery

After the route-table drift is repaired, private workloads still cannot reach S3 and DynamoDB through the private AWS paths expected by the platform contract. Endpoint coverage is incomplete across private route tables.

Recover the gateway endpoint configuration so that:

- the S3 gateway VPC endpoint is attached to every private route table;
- the DynamoDB gateway VPC endpoint is attached to every private route table;
- public route tables are excluded from these private-only endpoint attachments;
- endpoint route-table attachments derive from stable private route-table identities rather than accidental list order;
- NAT routes are not used as a workaround for missing gateway endpoint coverage;
- the existing endpoint resources are preserved and not deleted or unnecessarily replaced.

Keep the earlier routing behavior intact while fixing endpoint coverage.
