output "vnet_id" {
  value = azurerm_virtual_network.spoke.id
}

output "subnet_ids" {
  value = {
    app  = azurerm_subnet.app.id
    data = azurerm_subnet.data.id
  }
}
