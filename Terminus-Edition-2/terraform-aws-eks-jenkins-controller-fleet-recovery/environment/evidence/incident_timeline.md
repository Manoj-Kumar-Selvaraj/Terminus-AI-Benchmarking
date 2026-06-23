# Incident timeline
09:05 UTC: JOC redeployed after an EKS module refactor.
09:09 UTC: Only one controller rejoined JOC; payments, risk, and platform folders report no executors.
09:15 UTC: Controller pods restarted on general nodes and lost job history.
09:23 UTC: Plugin bootstrap attempted public update-center downloads blocked by policy.
09:36 UTC: Rollback plan shows protected cluster/Jenkins resources would be replaced.
