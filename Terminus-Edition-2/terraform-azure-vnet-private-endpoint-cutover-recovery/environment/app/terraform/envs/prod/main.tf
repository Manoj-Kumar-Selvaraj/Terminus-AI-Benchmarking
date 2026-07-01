terraform {
  required_version = ">= 1.5.0"
  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 3.110"
    }
  }
}

provider "azurerm" {
  features {}
  skip_provider_registration = true
}

module "secure_vnet" {
  source              = "../../modules/secure-vnet"
  name                = "pay-prod-spoke"
  location            = "eastus"
  resource_group_name = "rg-pay-prod-network"
  vnet_address_space  = ["10.42.0.0/16"]
  firewall_private_ip = "10.42.255.4"

  subnets = {
    app = {
      address_prefixes    = ["10.42.10.0/24"]
      tier                = "app"
      route_table_enabled = true
      nsg_enabled         = true
    }
    data = {
      address_prefixes    = ["10.42.20.0/24"]
      tier                = "data"
      route_table_enabled = true
      nsg_enabled         = true
    }
    private-endpoints = {
      address_prefixes    = ["10.42.30.0/24"]
      tier                = "private_endpoint"
      route_table_enabled = false
      nsg_enabled         = false
    }
    AzureBastionSubnet = {
      address_prefixes    = ["10.42.40.0/26"]
      tier                = "platform"
      route_table_enabled = false
      nsg_enabled         = false
    }
  }

  private_endpoint_subnet_key = "private-endpoints"
  private_endpoints = {
    storage_blob = {
      target_resource_id = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-pay-prod-data/providers/Microsoft.Storage/storageAccounts/payprodsa"
      subresource_names  = ["blob"]
      dns_zone_key       = "blob"
    }
    key_vault = {
      target_resource_id = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-pay-prod-security/providers/Microsoft.KeyVault/vaults/pay-prod-kv"
      subresource_names  = ["vault"]
      dns_zone_key       = "keyvault"
    }
  }

  application_gateway_subnet_cidr = "10.42.5.0/24"
  app_ports                      = [443, 8443]
  log_analytics_workspace_id     = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-monitor/providers/Microsoft.OperationalInsights/workspaces/pay-prod-law"
  tags = {
    environment = "prod"
    workload    = "payments"
    owner       = "platform-network"
  }
}
