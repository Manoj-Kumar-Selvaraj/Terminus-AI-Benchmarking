# Incident timeline

At 09:41 UTC, tenant `bulk-importer` began a scheduled replay and consumed the gateway allowance. At 09:42 UTC, low-volume tenants with no recent traffic began receiving HTTP 429 responses. The policy service still reported a burst of eight requests and a refill rate of four requests per second for every tenant.

At 10:17 UTC, the host clock stepped backwards during an NTP correction. The affected process immediately admitted another burst even though no forward interval had elapsed. A later rollback restored the previous client version, whose requests do not send `X-Tenant-ID`; those calls began returning `tenant_required` rather than reaching the partner endpoint.
