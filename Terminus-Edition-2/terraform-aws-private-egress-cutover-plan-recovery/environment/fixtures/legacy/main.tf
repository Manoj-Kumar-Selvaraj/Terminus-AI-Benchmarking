terraform {
  required_version = ">= 1.8.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.83"
    }
  }
}

provider "aws" {
  region                      = var.region
  access_key                  = "test"
  secret_key                  = "test"
  skip_credentials_validation = true
  skip_metadata_api_check     = true
  skip_requesting_account_id  = true
  skip_region_validation      = true
}

variable "region" { type = string }
variable "account_id" { type = string }
variable "nat_enabled_azs" {
  type    = set(string)
  default = []
}

module "egress" {
  source = "../../modules/private_egress"

  name_prefix            = "pay-egress"
  region                 = var.region
  account_id             = var.account_id
  vpc_cidr               = "10.42.0.0/16"
  nat_enabled_azs        = var.nat_enabled_azs
  runtime_queue_name     = "payments-runtime-events"
  allowed_principal_arns = ["arn:aws:iam::${var.account_id}:role/payments-runtime", "arn:aws:iam::${var.account_id}:role/payment-reconciler"]
  artifact_bucket_arns   = ["arn:aws:s3:::payments-prod-artifacts", "arn:aws:s3:::payments-prod-artifacts/*"]

  azs = {
    use1a = {
      az                 = "${var.region}a"
      public_cidr        = "10.42.1.0/24"
      app_cidr           = "10.42.11.0/24"
      data_cidr          = "10.42.21.0/24"
      corporate_dns_cidrs = ["10.200.0.0/16", "10.201.0.0/16"]
    }
    use1b = {
      az                 = "${var.region}b"
      public_cidr        = "10.42.2.0/24"
      app_cidr           = "10.42.12.0/24"
      data_cidr          = "10.42.22.0/24"
      corporate_dns_cidrs = ["10.200.0.0/16", "10.201.0.0/16"]
    }
    use1c = {
      az                 = "${var.region}c"
      public_cidr        = "10.42.3.0/24"
      app_cidr           = "10.42.13.0/24"
      data_cidr          = "10.42.23.0/24"
      corporate_dns_cidrs = ["10.200.0.0/16", "10.201.0.0/16"]
    }
  }

  tags = {
    Application = "payments"
    Environment = "prod"
    ManagedBy = "terraform"
  }
}

output "egress_route_matrix" { value = module.egress.egress_route_matrix }
output "endpoint_services" { value = module.egress.endpoint_services }
output "security_summary" { value = module.egress.security_summary }
