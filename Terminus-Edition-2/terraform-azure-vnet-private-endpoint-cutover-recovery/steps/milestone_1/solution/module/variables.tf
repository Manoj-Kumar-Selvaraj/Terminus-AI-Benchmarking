variable "name" {
  type = string
}

variable "resource_group_name" {
  type = string
}

variable "location" {
  type = string
}

variable "vnet_address_space" {
  type = list(string)
}

variable "tags" {
  type    = map(string)
  default = {}
}

variable "subnets" {
  type = map(object({
    address_prefixes    = list(string)
    tier                = string
    route_table_enabled = optional(bool, true)
    nsg_enabled         = optional(bool, true)
  }))

  validation {
    condition     = length(var.subnets) > 0
    error_message = "At least one subnet must be declared."
  }
}

variable "firewall_private_ip" {
  type = string

  validation {
    condition     = can(cidrhost("${var.firewall_private_ip}/32", 0))
    error_message = "firewall_private_ip must be a valid IPv4 address."
  }
}

variable "private_endpoint_subnet_key" {
  type    = string
  default = "private-endpoints"
}
