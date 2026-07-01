output "vnet_id" {
  value = azurerm_virtual_network.spoke.id
}

output "subnet_ids" {
  value = {
    for k, subnet in azurerm_subnet.spoke : k => subnet.id
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
