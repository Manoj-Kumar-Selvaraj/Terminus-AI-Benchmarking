Extend `/app/scripts/reconcile.sh` so allowed match desks come from `/app/config/channels.csv` instead of a hardcoded list. That file has columns `desk,enabled`; treat a desk as allowed only when `enabled` is `true` (case-insensitive). Canonicalize each desk value before checking the allowlist, using milestone 2 aliases (`FR`, `WEB`, `APP`) plus the new waiver alias `KSK` for `FRONT`.

All milestone 1–3 behavior remains in force: full `fine_id` equality, `patron_id` and `amount_cents` gates, `ASSESSED` status, desk equality after canonicalization, fine row consumption, calendar eligibility on `waiver_date` and `due_date`, the two-open-day window through `due_date`, latest `due_date` selection, and equal-date tie-breaking by earliest fine input row. Matched report rows must still emit canonical uppercase desks; unmatched rows leave `desk` blank. Summary amounts stay positive integer cents.

When `channels.csv` disables a desk such as `KIOSK` or `OTHER`, fines carrying those desks must not match even if the waiver names the same desk.

Continue to write `/app/out/waiver_report.csv` and `/app/out/waiver_summary.json` with the same schemas, status labels, blank unmatched fields, and summary keys from the earlier milestone.
