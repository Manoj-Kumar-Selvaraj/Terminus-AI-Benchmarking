# Milestone 4 — Preserve master/risk atomicity for credit-limit updates

The remaining incident symptom is a DB2 unit-of-work bug in credit-limit updates. A `LIM` detail touches both the financial master row and the risk profile row. When the risk profile update fails with SQLCODE `-530`, the master limit is already changed, leaving master/risk drift.

Review `/app/docs/db2_simulator_contract.md`, `/app/docs/fixed_width_layout.md`, and sample `/app/data/batches/limit_045.fb`. Repair `/app/internal/finbulk/profile.go` and `/app/internal/finbulk/runner.go`.

For this milestone, repair credit-limit unit-of-work behavior:

- a `LIM` detail must update `master.credit_limit_cents` and `risk.exposure_limit_cents` atomically;
- if either side returns `+100`, `-911`, or `-530`, neither side may be partially changed;
- `-530` should be a business reject, not an applied event;
- valid `LIM` details must still write audit/applied-event markers exactly once;
- all milestone 1–3 behavior must remain intact.

Do not change the JSON schema, fixed-width input format, run command, or simulator SQLCODE meanings.
