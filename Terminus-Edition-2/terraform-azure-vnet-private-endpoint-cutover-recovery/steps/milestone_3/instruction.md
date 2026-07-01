# Milestone 3 — repair NSG and route-table security boundaries

Security review found that the refactor could allow broad Internet ingress and did not preserve tier-specific subnet boundaries. Preserve the previous routing and Private DNS fixes while creating NSGs only for subnets where NSG attachment is enabled, associating each NSG back to the subnet with the same logical key.

Application subnet ingress must be allowed only from the application gateway subnet CIDR on the configured app ports, and data-tier ingress must be allowed only from app subnet prefixes on approved data ports. Add an explicit deny for Internet-origin inbound traffic, do not create broad allow rules from Internet, `*`, or `0.0.0.0/0`, and keep forced-egress route tables with BGP route propagation disabled.
