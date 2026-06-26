# Restore private placement without identity churn

After provenance was corrected, replacement capacity still appeared with public addresses, an internet-facing admin rule, and unstable subnet placement when the subnet list was reordered.

Preserve milestone 1. Use `/app/docs/network_contract.md`, `/app/docs/module_contract.md`, and the evidence to repair placement and security boundaries.

## Required behavior

- Every instance remains in an eligible `private_app` subnet in the configured account and has no public IP.
- Capacity is balanced across unique eligible availability zones.
- Stable logical slots retain their subnet when input ordering changes or another eligible zone is added.
- Scale-out creates only the newly required slots and preserves existing instance identities.
- Reject duplicate subnet IDs, duplicate zones, public tiers, cross-account subnets, insufficient zone count, malformed security-group IDs, malformed or duplicate prefix-list IDs, and invalid service ports with the field-specific error fragments in `/app/docs/network_contract.md`.
- Ingress and egress use the exact rule shapes from `/app/docs/network_contract.md`, including `source_security_group_id`, sorted `prefix_list_ids`, and the configured service port.
- Preserve all milestone 1 release and compatibility behavior.

Do not solve placement by list position, add public CIDRs, serialize capacity into one subnet, or hardcode the provided subnet IDs.
