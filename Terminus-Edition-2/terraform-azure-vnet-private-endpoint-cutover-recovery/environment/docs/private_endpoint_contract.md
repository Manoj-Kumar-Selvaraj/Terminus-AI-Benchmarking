# Private endpoint contract

Private endpoints must be declared from `var.private_endpoints` and attached only to the configured private endpoint subnet key. DNS zone groups and subresource names must remain data-driven.

Plans must not leave public ingress paths on private endpoint subnets or attach endpoints to routeable workload subnets.
