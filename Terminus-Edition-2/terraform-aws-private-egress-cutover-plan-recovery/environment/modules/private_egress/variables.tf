variable "name_prefix" { type = string }
variable "region" { type = string }
variable "account_id" { type = string }
variable "vpc_cidr" { type = string }
variable "azs" {
  type = map(object({
    az                    = string
    public_cidr           = string
    app_cidr              = string
    data_cidr             = string
    corporate_dns_cidrs    = list(string)
  }))
}
variable "nat_enabled_azs" {
  type    = set(string)
  default = []
}
variable "allowed_principal_arns" { type = list(string) }
variable "artifact_bucket_arns" { type = list(string) }
variable "runtime_queue_name" { type = string }
variable "tags" {
  type    = map(string)
  default = {}
}
