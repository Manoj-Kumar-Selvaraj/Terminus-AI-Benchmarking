Extend `/app/lib/reconcile.rb` with client refund limits from `/app/config/client_limits.csv` while
keeping all previous behavior. The limits file is header-addressed and includes `client_id`,
`service_area`, `max_refund_cents`, `enabled`, and optional `allow_any` columns; extra columns are
ignored. Trim all fields. A row is well formed only when `client_id` is nonblank, `service_area`
canonicalizes through the runtime alias map to `MASSAGE`, `FACIAL`, or `SAUNA`, `max_refund_cents`
is a positive base-10 integer, and `enabled` is `true` or `false` case-insensitively. If `allow_any`
is present it must be `true` or `false`; if it is absent, treat it as `false`. Malformed `allow_any`
values invalidate the policy row. The last well-formed row for a `(client_id, canonical service_area)`
key is authoritative.

Apply client-limit policy while walking eligible unused appointments in priority order (same
latest-date, ANY priority, and earliest-row rules as before). For each candidate in that order,
require an enabled exact `(client_id, canonical service_area)` limit row; the refund `amount_cents`
must be less than or equal to `max_refund_cents` (amounts exactly equal to the cap are allowed). For
`ANY` refund rows, the limit row for the candidate service must also have `allow_any = true`. If a
candidate fails these checks, skip it without consuming its appointment row and continue to the
next-best eligible appointment. Missing, disabled, malformed, wrong-client, wrong-service,
over-limit, or non-true `allow_any` policy rows make that candidate ineligible without consuming the
appointment row. Client limits do not bypass any prior identity, amount, alias, service-policy, date,
status, or consumption gate.
Preserve all report and summary contracts and continue regenerating
`/app/out/appointment_selection.csv` under the established dated trace schema.
