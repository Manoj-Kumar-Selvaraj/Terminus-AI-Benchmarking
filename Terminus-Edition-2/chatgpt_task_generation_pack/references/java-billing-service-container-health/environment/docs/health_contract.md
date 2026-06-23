# Health contract

The billing microservice exposes two HTTP health endpoints on port 8080.

`/health/live` answers whether the JVM process and HTTP listener are alive. It must
not wait for database migrations or datasource warmup. Container liveness probes
should target this endpoint.

`/health/ready` answers whether the service can serve billing traffic. It must
confirm migration completion and datasource connectivity before returning UP.

Readiness may remain DOWN while migrations run. Liveness must not treat that state
as a failed container.
