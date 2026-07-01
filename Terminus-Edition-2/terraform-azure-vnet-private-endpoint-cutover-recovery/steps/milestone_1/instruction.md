# Milestone 1 — recover subnet-driven forced egress

The production VNet module was refactored during a private-endpoint cutover, and the reviewed plan shows app/data workload subnets drifting back to hard-coded legacy resources with Internet egress. Repair the reusable module under `/app/terraform/modules/secure-vnet`; it must not own the provider or shared resource group, and subnet creation must be driven from `var.subnets` while preserving each logical key for downstream maps.

Route tables and default routes must be created only for routeable workload subnets, excluding AzureFirewallSubnet, GatewaySubnet, AzureBastionSubnet and the private endpoint subnet. The default route must be `0.0.0.0/0` through `VirtualAppliance` using `var.firewall_private_ip`, never `Internet`, and the module must keep the `vnet_id` and `subnet_ids` output shape while validating that the firewall IP cannot be empty or malformed.
