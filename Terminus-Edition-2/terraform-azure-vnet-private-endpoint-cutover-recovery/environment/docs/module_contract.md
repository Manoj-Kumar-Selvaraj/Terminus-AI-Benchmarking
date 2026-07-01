# Secure VNet module contract

The `secure-vnet` module under `/app/terraform/modules/secure-vnet` models a production-style Azure hub/spoke VNet with data-driven subnets, firewall virtual-appliance default routes, private endpoint placement, and downstream-compatible outputs.

Recovery is configuration and module focused. Agents repair Terraform under `/app/terraform` without introducing `terraform apply` shortcuts or hardcoded legacy subnet singletons.
