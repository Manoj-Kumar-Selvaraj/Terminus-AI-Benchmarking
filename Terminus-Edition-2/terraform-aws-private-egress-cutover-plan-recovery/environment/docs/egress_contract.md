# Egress contract

Application subnets route `0.0.0.0/0` to the NAT gateway in the same availability zone. Data subnets remain isolated and must not gain module-owned default internet routes.

Missing same-AZ NAT coverage for an enabled AZ is a validation failure. The diagnostic must clearly identify NAT coverage, preferably with the phrase `same-AZ NAT`, so operators can distinguish this precondition from unrelated route-table errors. Corporate DNS CIDRs must be scoped per AZ inputs rather than hardcoded literals.

Subnets and route tables use `Tier` tags with exact values `public`, `app`, and `data`. Public subnets may set `map_public_ip_on_launch = true`; app and data subnets must keep it false. App default routes are represented by `aws_route.app_default` keyed by AZ and directly reference the same-key NAT gateway expression, for example `aws_nat_gateway.az[each.key].id`. Do not create `aws_route.data_default`.

Legacy continuity requires six per-AZ keyed `moved` blocks for the original private subnet and private route-table resources. Use the exact keyed address shape for each legacy AZ key:

```hcl
moved {
  from = aws_subnet.private["use1a"]
  to   = aws_subnet.app["use1a"]
}

moved {
  from = aws_route_table.private["use1a"]
  to   = aws_route_table.app["use1a"]
}
```

Repeat the same private-to-app subnet and route-table mappings for `use1b` and `use1c`. Do not leave `resource "aws_subnet" "private"`, `resource "aws_route_table" "private"`, or `resource "aws_route" "data_default"` in the final module source.
