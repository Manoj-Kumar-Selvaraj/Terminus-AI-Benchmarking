Add program policy from `/app/config/methods.csv` to `/app/cmd/reconcile/main.go`. The verifier builds the binary and runs it with no command-line arguments using the fixed input and output paths from earlier milestones. Preserve full `pass_id` matching, `ACTIVE` status, single-use pass rows, aliases, open `credit_date` rules, and undated CSV compatibility.

Enabled programs come from `methods.csv` rows with trimmed, case-insensitive `enabled=true`. Disabled programs never match. Lower numeric `priority` ranks earlier; malformed priorities sort after numeric values.

Credit `program` may be `ANY` (never emitted; matches any enabled pass satisfying identity, guest, amount, status, dates, and consumption) or blank (matches any enabled pass without priority ordering). For `ANY`, pick latest `valid_until`, then lower priority, then earliest pass row. For blank, pick latest `valid_until` or earliest row when undated. Disabled pass programs stay ineligible for `ANY` and blank credits. Concrete programs require exact canonical match.

On matched rows emit the canonical credit program after alias normalization, except `ANY` and blank credits emit the selected pass canonical program. Keep report columns `pass_id,guest_id,program,amount_cents,status`, blank `program` on unmatched rows, and the same summary JSON schema.
