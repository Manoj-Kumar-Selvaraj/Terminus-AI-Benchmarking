Update `/app/app/reconcile.rb` so legacy pass tier aliases normalize before matching. Keep every prior gate: full identity equality, `SCANNED` status, allowed reasons, window and timestamp rules, row consumption, and latest-`scan_ts` then earliest-row tie-breaking. Map correction and session `pass_tier` values after trim and case fold: `HR` to `DAY`, `QR` to `SEASON`, and `CC` to `VIP`.

From this step onward, eligible canonical tiers are `DAY`, `SEASON`, and `VIP`. Unknown normalized values stay unmatched even when both sides share the same unknown code. Matched rows emit the canonical session `pass_tier`; unmatched rows leave `pass_tier` blank.

Continue writing `/app/out/lift_gate_release_report.csv` and `/app/out/lift_gate_release_summary.txt` with the same header, status values, correction order, and positive integer summary totals as before.
