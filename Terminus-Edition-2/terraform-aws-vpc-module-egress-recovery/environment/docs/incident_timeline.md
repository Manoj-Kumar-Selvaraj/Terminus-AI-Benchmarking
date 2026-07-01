# Incident timeline

Workers in `prod-app-b` and `prod-app-c` showed elevated cross-AZ NAT bytes after a VPC module refactor. Database subnets then showed unexpected default-route traffic. Gateway endpoints looked healthy in logs but were attached to non-app route tables. Security blocked the fourth-AZ rollout until flow logs, resolver boundaries, and import-state behavior were proven.


## Additional noisy evidence

`/app/evidence/production_vpc_recovery.log` is intentionally long and noisy, with repeated INFO/WARN/ERROR lines from route propagation, endpoint inventory, flow-log polling, and AWS SDK retries. Operators must correlate the structured inventories with the logs; a single visible error line is not sufficient evidence for a safe repair.
