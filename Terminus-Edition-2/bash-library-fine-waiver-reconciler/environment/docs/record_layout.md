# Record Layouts

Fines use `fine_id,patron_id,amount_cents,status,desk` and may include `due_date`.

Waivers use `fine_id,patron_id,amount_cents,desk` and may include `waiver_date`.

Allowed desks are defined in `/app/config/channels.csv`. See `/app/docs/desk_allowlist.md` for alias rules and `/app/docs/date_gating.md` for calendar and open-day window behavior.

Report schema: `fine_id,patron_id,desk,amount_cents,status`.

Summary schema: `matched_count`, `matched_amount_cents`, `unmatched_count`, `unmatched_amount_cents` (positive integer cents).
