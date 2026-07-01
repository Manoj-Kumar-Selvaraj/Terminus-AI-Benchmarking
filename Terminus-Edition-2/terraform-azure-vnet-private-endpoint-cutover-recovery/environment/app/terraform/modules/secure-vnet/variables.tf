variable "name" { type = string }
variable "resource_group_name" { type = string }
variable "location" { type = string }
variable "vnet_address_space" { type = list(string) }
variable "tags" { type = map(string) default = {} }

variable "subnets" {
  type = map(object({
    address_prefixes     = list(string)
    tier                 = string
    route_table_enabled  = optional(bool, true)
    nsg_enabled          = optional(bool, true)
  }))
}

variable "firewall_private_ip" { type = string }
variable "private_endpoint_subnet_key" { type = string default = "private-endpoints" }
variable "private_endpoints" { type = map(any) default = {} }
variable "application_gateway_subnet_cidr" { type = string default = "10.80.0.0/24" }
variable "app_ports" { type = list(number) default = [443] }
variable "log_analytics_workspace_id" { type = string default = "" }
variable "enable_ddos_protection" { type = bool default = false }
variable "ddos_protection_plan_id" { type = string default = "" }
variable "allowed_admin_cidrs" { type = list(string) default = ["0.0.0.0/0"] }
