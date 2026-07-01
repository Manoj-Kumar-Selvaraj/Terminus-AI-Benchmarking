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

variable "private_endpoints" {
  type = map(object({
    target_resource_id = string
    subresource_names  = list(string)
    dns_zone_key       = string
  }))
  default = {}
}

variable "application_gateway_subnet_cidr" {
  type    = string
  default = "10.80.0.0/24"
}

variable "app_ports" {
  type    = list(number)
  default = [443]

  validation {
    condition     = alltrue([for port in var.app_ports : port > 0 && port < 65536])
    error_message = "app_ports must contain valid TCP port numbers."
  }
}

variable "log_analytics_workspace_id" {
  type    = string
  default = ""
}

variable "enable_ddos_protection" {
  type    = bool
  default = false
}

variable "ddos_protection_plan_id" {
  type    = string
  default = ""
}

variable "allowed_admin_cidrs" {
  type    = list(string)
  default = []

  validation {
    condition     = alltrue([for cidr in var.allowed_admin_cidrs : cidr != "0.0.0.0/0" && cidr != "::/0"])
    error_message = "Administrator CIDR ranges must not include 0.0.0.0/0 or ::/0."
  }
}
