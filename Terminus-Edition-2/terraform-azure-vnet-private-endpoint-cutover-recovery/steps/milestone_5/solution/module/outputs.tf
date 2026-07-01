output "vnet_id" {
  value = azurerm_virtual_network.spoke.id
}

output "vnet_name" {
  value = azurerm_virtual_network.spoke.name
}

output "subnet_ids" {
  value = {
    for k, subnet in azurerm_subnet.spoke : k => subnet.id
  }
}

output "route_table_ids" {
  value = {
    for k, route_table in azurerm_route_table.spoke : k => route_table.id
  }
}

output "nsg_ids" {
  value = {
    for k, nsg in azurerm_network_security_group.spoke : k => nsg.id
  }
}

output "private_dns_zone_ids" {
  value = {
    for k, zone in azurerm_private_dns_zone.private : k => zone.id
  }
}

output "private_endpoint_ids" {
  value = {
    for k, endpoint in azurerm_private_endpoint.endpoint : k => endpoint.id
  }
}
