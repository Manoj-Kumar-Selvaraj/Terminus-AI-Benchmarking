# Incident timeline

Workers in `prod-app-b` and `prod-app-c` showed elevated cross-AZ NAT bytes after a VPC module refactor. Database subnets then showed unexpected default-route traffic. Gateway endpoints looked healthy in logs but were attached to non-app route tables. Security blocked the fourth-AZ rollout until flow logs, resolver boundaries, and import-state behavior were proven.
