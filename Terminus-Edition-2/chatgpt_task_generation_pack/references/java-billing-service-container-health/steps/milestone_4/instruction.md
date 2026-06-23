A schema migration release lengthened startup and the platform began restarting billing pods before the rollout finished. Review `/app/evidence/kube_events.txt`, `/app/docs/health_contract.md`, and `/app/deploy/kube/billing-deployment.yaml`. Make startup survive the migration window without removing migrations or readiness checks.

Preserve prior datasource, pool, and JVM fixes. The verifier checks that `/health/live` stays UP during migration while `/health/ready` remains DOWN until migration completes, and that liveness probing targets the correct endpoint with adequate startup timing.
