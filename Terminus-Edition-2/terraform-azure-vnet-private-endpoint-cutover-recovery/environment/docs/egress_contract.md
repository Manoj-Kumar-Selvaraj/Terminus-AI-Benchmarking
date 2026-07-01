# Egress contract

Routeable subnets must associate to per-subnet route tables with `0.0.0.0/0` pointing to the firewall private IP using `next_hop_type = "VirtualAppliance"`.

Platform subnets such as `AzureFirewallSubnet`, `GatewaySubnet`, and `AzureBastionSubnet` must be excluded from route-table association logic.
