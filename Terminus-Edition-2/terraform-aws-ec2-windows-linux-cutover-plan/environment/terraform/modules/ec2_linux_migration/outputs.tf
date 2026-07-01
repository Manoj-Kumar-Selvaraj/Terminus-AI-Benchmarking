output "planned_linux_instances" {
  description = "Linux replacement instance plan keyed by workload."
  value       = {}
}

output "planned_data_volumes" {
  description = "Data volume plan keyed by workload and Linux device name."
  value       = {}
}
