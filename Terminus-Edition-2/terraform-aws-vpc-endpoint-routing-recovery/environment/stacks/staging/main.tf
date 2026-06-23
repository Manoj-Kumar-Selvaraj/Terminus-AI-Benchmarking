terraform {
  required_version = ">= 1.5.0"
}

module "network" {
  source          = "../../modules/network"
  environment     = "staging"
  vpc_cidr_block  = "10.42.0.0/16"
}

output "network" {
  value = module.network
}
