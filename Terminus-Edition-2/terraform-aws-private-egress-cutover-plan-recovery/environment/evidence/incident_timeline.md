# Incident timeline

The payments platform VPC module was refactored during a private-egress cutover. The cutover was stopped before apply after reviewers noticed that the plan still had mixed egress semantics: application route tables were not consistently tied to the NAT gateway in their own availability zone, data subnet route tables were gaining outbound routes, and some PrivateLink resources were planned with public-facing or wildcard policy shapes.

The platform team cannot run `terraform apply` during the exercise. Recovery is accepted only when `terraform validate`, `terraform plan -refresh=false`, and `terraform show -json` prove that the module would converge to the intended plan without live AWS reads.
