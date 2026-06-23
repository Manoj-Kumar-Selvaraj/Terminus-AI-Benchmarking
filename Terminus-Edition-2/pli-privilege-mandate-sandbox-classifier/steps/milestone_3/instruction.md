The classifier must enforce `/app/config/sandbox_windows.psv`, whose columns are `service_id|open_ts|close_ts|state`. Keep all existing full-key, alias, eligibility, ordering, consumption, report, and summary behavior.

`recv_ts`, `audit_ts`, `open_ts`, and `close_ts` must each be numeric 14-digit UTC timestamps. A candidate qualifies only when one window has the same trimmed, case-insensitive `service_id`, its state equals `OPEN_SANDBOX_STATE` case-insensitively, and both the mandate `recv_ts` and audit `audit_ts` are inside that same inclusive window. Also require `recv_ts <= audit_ts`. Missing, malformed, reversed, closed, wrong-service, before-open, and after-close cases are `DENIED`.

When several unused candidates remain eligible, choose the greatest `recv_ts`, then the earliest mandate input row. Consumption carries across audits in audit input order.

Continue writing `/app/out/mandate_report.csv` with header `claim_id|mandate_id|service_id|audit_class|sandbox_class|cap_token|verdict_code|status` and `/app/out/mandate_summary.txt` with exactly `authorized_count`, `authorized_mandates`, `denied_count`, and `denied_mandates`. Emit canonical `sandbox_class` only for `AUTHORIZED`, blank it for `DENIED`, and use only `AUTHORIZED` or `DENIED` as status.
