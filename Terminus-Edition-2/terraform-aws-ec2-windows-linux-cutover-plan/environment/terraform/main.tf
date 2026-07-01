module "ec2_linux_migration" {
  source = "./modules/ec2_linux_migration"

  region                   = var.region
  common_tags              = var.common_tags
  migration_defaults       = var.migration_defaults
  legacy_windows_instances = var.legacy_windows_instances
}
