The billing microservice pods report ready=0 while the Java process keeps running and `/health/live` answers on port 8080. Review `/app/evidence/incident.log`, `/app/docs/health_contract.md`, and the service configuration under `/app/config`. Restore readiness so invoice traffic can be served without changing the live endpoint contract.

The verifier starts the billing stack, expects `/health/ready` to return UP after startup migration completes, and checks that `GET /api/invoices` returns the seeded invoice row.
