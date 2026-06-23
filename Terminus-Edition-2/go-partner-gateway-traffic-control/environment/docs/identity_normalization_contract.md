# Tenant identity normalization contract

Explicit tenant identifiers are normalized by trimming surrounding ASCII/Unicode whitespace and comparing the remaining value case-insensitively. Values such as ` Partner-A `, `partner-a`, and `PARTNER-A` therefore consume the same admission budget.

Normalization must happen before bucket lookup or creation. The gateway must not maintain parallel buckets for differently cased or padded forms of one explicit identity.

The implicit identity used for requests with an absent or blank `X-Tenant-ID` header is an internal compatibility identity. It must not collide with any explicit header value, including the literal text `legacy-default`.
