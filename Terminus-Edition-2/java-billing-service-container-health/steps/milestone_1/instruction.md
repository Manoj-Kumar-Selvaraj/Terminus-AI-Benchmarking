The billing microservice pods report ready=0 while the Java process keeps running and `/health/live` answers on port 8080. Review `/app/evidence/incident.log`, `/app/docs/health_contract.md`, and the service configuration under `/app/config`. Restore readiness so invoice traffic can be served without changing the live endpoint contract.

After the fix, `/health/ready` must return HTTP 200 with body `UP` once startup migration completes. `GET /api/invoices` must return HTTP 200 with a plain-text CSV body that includes the seeded row `inv-100,acct-1,2500` (columns: invoice id, account id, amount in cents).

The service must keep running the real billing JAR started by `/app/scripts/run_service.sh` (do not replace it with a mock HTTP server). After readiness is UP and the request completes, `GET /internal/pool` must report `max=5` matching `billing.pool.max` in `/app/config/application.properties` and `active=0`.
