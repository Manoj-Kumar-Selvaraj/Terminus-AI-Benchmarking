# Incident notes: staging network refactor recovery

A shared Terraform networking module was refactored to reduce duplicated route
and endpoint declarations. The first staging review after the refactor did not
contact AWS; it used saved plan JSON, state snapshots, reachability probes, and
consumer fixtures.

Observed symptoms:

1. The staging plan shows route-table association churn under private subnets.
   The reachability report shows private workloads losing their expected NAT
   egress path.
2. After route-table drift is corrected in a local patch, private workloads still
   cannot reach S3 and DynamoDB through private AWS paths. Endpoint coverage is
   incomplete on private route tables.
3. Security review finds public ingress on the shared interface endpoint security
   group, and one interface endpoint appears in a public subnet with private DNS
   behavior no longer matching the endpoint design.
4. Downstream stacks still fail because old module output names were removed.
   The saved migration plan also attempts replacement of stable network
   resources that should be preserved during this recovery.

Use the module HCL, docs, and fixtures under `/app` to recover the module. Do not
edit evidence or fixture files to hide the incident.
