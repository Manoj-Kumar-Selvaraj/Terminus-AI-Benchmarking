locals {
  common_tags = var.tags

  platform_subnet_keys = toset([
    "AzureFirewallSubnet",
    "GatewaySubnet",
    "AzureBastionSubnet",
    var.private_endpoint_subnet_key,
  ])

  routeable_subnets = {
    for key, subnet in var.subnets : key => subnet
    if try(subnet.route_table_enabled, true) && !contains(local.platform_subnet_keys, key)
  }
}

resource "azurerm_virtual_network" "spoke" {
  name                = var.name
  location            = var.location
  resource_group_name = var.resource_group_name
  address_space       = var.vnet_address_space
  tags                = local.common_tags
}

resource "azurerm_subnet" "spoke" {
  for_each = var.subnets

  name                                      = each.key
  resource_group_name                       = var.resource_group_name
  virtual_network_name                      = azurerm_virtual_network.spoke.name
  address_prefixes                          = each.value.address_prefixes
  private_endpoint_network_policies         = each.key == var.private_endpoint_subnet_key ? "Disabled" : "Enabled"
}

resource "azurerm_route_table" "spoke" {
  for_each = local.routeable_subnets

  name                          = "${var.name}-${each.key}-rt"
  location                      = var.location
  resource_group_name           = var.resource_group_name
  disable_bgp_route_propagation = true
  tags                          = local.common_tags
}

resource "azurerm_route" "default_egress" {
  for_each = local.routeable_subnets

  name                   = "default-to-firewall"
  resource_group_name    = var.resource_group_name
  route_table_name       = azurerm_route_table.spoke[each.key].name
  address_prefix         = "0.0.0.0/0"
  next_hop_type          = "VirtualAppliance"
  next_hop_in_ip_address = var.firewall_private_ip
}

resource "azurerm_subnet_route_table_association" "spoke" {
  for_each = local.routeable_subnets

  subnet_id      = azurerm_subnet.spoke[each.key].id
  route_table_id = azurerm_route_table.spoke[each.key].id
}
