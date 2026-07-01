output "vnet_id" {
  value = azurerm_virtual_network.spoke.id
}

output "subnet_ids" {
  value = {
    for k, subnet in azurerm_subnet.spoke : k => subnet.id
  }
}
