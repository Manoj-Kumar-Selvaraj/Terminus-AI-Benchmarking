locals {
  common_tags = var.tags
}

resource "azurerm_virtual_network" "spoke" {
  name                = var.name
  location            = var.location
  resource_group_name = var.resource_group_name
  address_space       = var.vnet_address_space
  tags                = local.common_tags
}

# Regression from the failed cutover: the module now models only two hard-coded
# subnets and sends all traffic directly to the Internet. Private endpoint DNS,
# subnet security, diagnostics and legacy migration metadata were dropped.
resource "azurerm_subnet" "app" {
  name                 = "app"
  resource_group_name  = var.resource_group_name
  virtual_network_name = azurerm_virtual_network.spoke.name
  address_prefixes     = ["10.42.1.0/24"]
}

resource "azurerm_subnet" "data" {
  name                 = "data"
  resource_group_name  = var.resource_group_name
  virtual_network_name = azurerm_virtual_network.spoke.name
  address_prefixes     = ["10.42.2.0/24"]
}

resource "azurerm_route_table" "default" {
  name                = "${var.name}-default"
  location            = var.location
  resource_group_name = var.resource_group_name
}

resource "azurerm_route" "internet" {
  name                   = "default-internet"
  resource_group_name    = var.resource_group_name
  route_table_name       = azurerm_route_table.default.name
  address_prefix         = "0.0.0.0/0"
  next_hop_type          = "Internet"
}

resource "azurerm_subnet_route_table_association" "app" {
  subnet_id      = azurerm_subnet.app.id
  route_table_id = azurerm_route_table.default.id
}
