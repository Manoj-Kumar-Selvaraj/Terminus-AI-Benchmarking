# Security review findings

- The shared interface endpoint security group currently allows TCP/443 from
  `0.0.0.0/0`.
- An IPv6 default ingress rule using `::/0` was also retained during the refactor.
- Required interface endpoints must be reachable from private application tiers,
  not placed into public subnets.
- Required SSM-family interface endpoints must keep private DNS enabled.
- Approved application sources are documented in `/app/fixtures/allowed_endpoint_sources.json`.
- The finding cannot be closed by adding a broader allow-all rule or by deleting
  interface endpoints.
