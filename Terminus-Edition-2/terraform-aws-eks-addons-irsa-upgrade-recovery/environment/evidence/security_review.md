# Security review finding
Add-on permissions must not move to node roles. EBS CSI and AWS Load Balancer Controller need IRSA roles. The private cluster endpoint and private subnet allocation are compliance constraints. Regulated workloads must run on on-demand capacity only.
