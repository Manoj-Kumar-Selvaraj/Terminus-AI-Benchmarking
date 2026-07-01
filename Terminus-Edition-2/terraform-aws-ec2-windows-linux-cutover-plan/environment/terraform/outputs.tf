output "planned_linux_instances" {
  description = "Linux replacement instances keyed by workload."
  value       = module.ec2_linux_migration.planned_linux_instances
}

output "planned_data_volumes" {
  description = "Data volume mapping keyed by workload and Linux device name."
  value       = module.ec2_linux_migration.planned_data_volumes
}
