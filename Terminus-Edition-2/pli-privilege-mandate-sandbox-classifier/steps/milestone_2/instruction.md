The classifier must accept legacy compare-key values declared by `ALIAS_*` rules in `/app/src/mandate_rules.pli`. Each declaration contains `raw=>canonical`. Trim and case-fold both sides of every compare key, then apply the configured mapping to mandate and audit values before matching. Unknown values remain distinct and must not fuzzy-match.

Keep the full-key, eligibility, ordering, numeric timestamp, candidate selection, one-time consumption, and summary behavior already implemented. Emit the selected mandate's canonical `sandbox_class` only for `AUTHORIZED`; keep it blank for `DENIED`.

Continue writing `/app/out/mandate_report.csv` with header `claim_id|mandate_id|service_id|audit_class|sandbox_class|cap_token|verdict_code|status` and `/app/out/mandate_summary.txt` with `authorized_count`, `authorized_mandates`, `denied_count`, and `denied_mandates`. Status remains exactly `AUTHORIZED` or `DENIED`. Do not apply sandbox windows yet.
