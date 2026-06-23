Extend the dated spa refund reconciler with service policy from `/app/config/methods.csv` while
keeping all previous behavior. The policy file is header-addressed and includes `service_area`,
`enabled`, and optional `priority` columns; extra columns are ignored. Service names use the same
canonicalization and runtime alias rules as refund rows. A policy row is well formed only when the
service is nonblank, canonicalizes to `MASSAGE`, `FACIAL`, or `SAUNA`, and `enabled` is `true` or
`false` case-insensitively. The last well-formed row for a canonical service is authoritative.
Disabled or missing services are not matchable. Priority is an integer where lower values rank
earlier; missing or malformed priorities rank after numeric priorities.

Refund rows may use `ANY`
as `service_area` starting in this step. `ANY` is not emitted in the report. It can match any
enabled appointment service that satisfies all identifier, client, amount, status, date, and
consumption rules. For `ANY`, select the unused eligible appointment with the latest `service_date`;
if dates tie, select the lower configured service priority; if priority also ties, select the
earliest appointment input row. Non-`ANY` refunds still require exact canonical service equality and
enabled policy. Keep output regeneration, schema, summary, alias, and invalid-row behavior
unchanged.
