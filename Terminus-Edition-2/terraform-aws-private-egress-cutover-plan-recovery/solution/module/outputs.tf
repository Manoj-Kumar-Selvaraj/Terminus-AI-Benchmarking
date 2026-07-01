output "egress_route_matrix" { value = local.egress_route_matrix }
output "endpoint_services" { value = sort(tolist(local.interface_endpoint_services)) }
output "security_summary" { value = local.security_summary }
output "flow_log_group_name" { value = aws_cloudwatch_log_group.flow.name }
output "runtime_queue_arn" { value = aws_sqs_queue.runtime.arn }
