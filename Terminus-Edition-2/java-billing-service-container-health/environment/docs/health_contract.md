# Health contract

The billing microservice exposes two HTTP health endpoints on port 8080.

`/health/live` answers whether the JVM process and HTTP listener are alive. It must
not wait for database migrations or datasource warmup. Container liveness probes
should target this endpoint.

`/health/ready` answers whether the service can serve billing traffic. It must
confirm migration completion and datasource connectivity before returning UP.

`GET /api/invoices` returns HTTP 200 with a plain-text CSV body. Each line is
`invoice_id,account_id,amount_cents`. The seeded migration row is
`inv-100,acct-1,2500`.

The billing service must run from `/app/build/billing-service.jar` via
`/app/scripts/run_service.sh` (not a mock HTTP listener). After readiness is
UP, `GET /internal/pool` returns plain-text JDBC pool counters:
`active=<n>`, `idle=<n>`, and `max=<n>` where `max` matches
`billing.pool.max` in `/app/config/application.properties`.

Readiness may remain DOWN while migrations run. Liveness must not treat that state
as a failed container.
