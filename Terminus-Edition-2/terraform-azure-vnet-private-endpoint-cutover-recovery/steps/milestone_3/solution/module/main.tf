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

  nsg_subnets = {
    for key, subnet in var.subnets : key => subnet
    if try(subnet.nsg_enabled, true)
  }

  app_subnets = {
    for key, subnet in var.subnets : key => subnet
    if lower(subnet.tier) == "app" && try(subnet.nsg_enabled, true)
  }

  data_subnets = {
    for key, subnet in var.subnets : key => subnet
    if lower(subnet.tier) == "data" && try(subnet.nsg_enabled, true)
  }

  app_subnet_prefixes = flatten([
    for subnet in values(local.app_subnets) : subnet.address_prefixes
  ])

  private_dns_zones = {
    blob       = "privatelink.blob.core.windows.net"
    queue      = "privatelink.queue.core.windows.net"
    keyvault   = "privatelink.vaultcore.azure.net"
    postgresql = "privatelink.database.windows.net"
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

resource "azurerm_private_dns_zone" "private" {
  for_each = local.private_dns_zones

  name                = each.value
  resource_group_name = var.resource_group_name
  tags                = local.common_tags
}

resource "azurerm_private_dns_zone_virtual_network_link" "spoke" {
  for_each = local.private_dns_zones

  name                  = "${var.name}-${each.key}-link"
  resource_group_name   = var.resource_group_name
  private_dns_zone_name = azurerm_private_dns_zone.private[each.key].name
  virtual_network_id    = azurerm_virtual_network.spoke.id
  registration_enabled  = false
  tags                  = local.common_tags
}

resource "azurerm_private_endpoint" "endpoint" {
  for_each = var.private_endpoints

  name                = "${var.name}-${each.key}-pe"
  location            = var.location
  resource_group_name = var.resource_group_name
  subnet_id           = azurerm_subnet.spoke[var.private_endpoint_subnet_key].id
  tags                = local.common_tags

  private_service_connection {
    name                           = "${var.name}-${each.key}-psc"
    private_connection_resource_id = each.value.target_resource_id
    subresource_names              = each.value.subresource_names
    is_manual_connection           = false
  }

  private_dns_zone_group {
    name                 = "default"
    private_dns_zone_ids = [azurerm_private_dns_zone.private[each.value.dns_zone_key].id]
  }
}

resource "azurerm_network_security_group" "spoke" {
  for_each = local.nsg_subnets

  name                = "${var.name}-${each.key}-nsg"
  location            = var.location
  resource_group_name = var.resource_group_name
  tags                = local.common_tags
}

resource "azurerm_subnet_network_security_group_association" "spoke" {
  for_each = local.nsg_subnets

  subnet_id                 = azurerm_subnet.spoke[each.key].id
  network_security_group_id = azurerm_network_security_group.spoke[each.key].id
}

resource "azurerm_network_security_rule" "allow_app_gateway_to_app" {
  for_each = local.app_subnets

  name                        = "Allow-AppGateway-To-App"
  priority                    = 110
  direction                   = "Inbound"
  access                      = "Allow"
  protocol                    = "Tcp"
  source_address_prefix       = var.application_gateway_subnet_cidr
  source_port_range           = "*"
  destination_address_prefix  = "*"
  destination_port_ranges     = [for port in var.app_ports : tostring(port)]
  resource_group_name         = var.resource_group_name
  network_security_group_name = azurerm_network_security_group.spoke[each.key].name
}

resource "azurerm_network_security_rule" "allow_app_to_data" {
  for_each = local.data_subnets

  name                         = "Allow-App-To-Data"
  priority                     = 120
  direction                    = "Inbound"
  access                       = "Allow"
  protocol                     = "Tcp"
  source_address_prefixes      = local.app_subnet_prefixes
  source_port_range            = "*"
  destination_address_prefix   = "*"
  destination_port_ranges      = ["1433", "5432", "6379"]
  resource_group_name          = var.resource_group_name
  network_security_group_name  = azurerm_network_security_group.spoke[each.key].name
}

resource "azurerm_network_security_rule" "deny_internet_inbound" {
  for_each = local.nsg_subnets

  name                        = "Deny-Internet-Inbound"
  priority                    = 4096
  direction                   = "Inbound"
  access                      = "Deny"
  protocol                    = "*"
  source_address_prefix       = "Internet"
  source_port_range           = "*"
  destination_address_prefix  = "*"
  destination_port_range      = "*"
  resource_group_name         = var.resource_group_name
  network_security_group_name = azurerm_network_security_group.spoke[each.key].name
}
