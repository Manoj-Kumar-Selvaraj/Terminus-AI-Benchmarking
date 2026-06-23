# Support Matrix

Canonical disbursement kinds: `SELLER`, `BROKER`, `TAX`. Legacy aliases accepted after the package-clearing milestone: `SLR`, `BRK`, and `TAXAUTH`. Alias lookup is case-insensitive after trim.

Group statuses: `CLEARED` and `HELD`. Use exactly one held reason token: `PACKAGE_NOT_OPEN`, `NO_MATCHED_ROWS`, `UNMATCHED_ACTION`, `MISSING_KIND:<KIND>` (first missing kind in `required_kinds` order), `TOTAL_MISMATCH`, `INSUFFICIENT_FUNDS`, or `CONTROL_TOTAL_MISMATCH`. Cleared rows use `OK`.

`NO_MATCHED_ROWS` applies only when a package has zero configured disbursement action rows. `UNMATCHED_ACTION` applies when action rows exist but at least one failed row-level hold matching (for example location mismatch). Control-total reconciliation is evaluated before trust funding; when both would fail, emit `CONTROL_TOTAL_MISMATCH`.

`required_kinds` and `matched_kinds` are pipe-separated (`SELLER|BROKER|TAX`).

Commit rows use `commit_id=COMMIT-<closing_id>` and `committed_at=20260613000000`. Checkpoint keys are `last_committed_closing_id`, `committed_count`, and `status` (`ABENDED` or `COMPLETE`).
