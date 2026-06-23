The privilege mandate sandbox classifier authorizes audits on partial key matches. Repair the editable PL/I control decks in `/app/src/mandate_batch.pli` and `/app/src/mandate_rules.pli` so `/app/data/sandbox_audits.psv` reconciles against `/app/data/mandates.psv`. Policy constants are `DCL ... INIT('value')` declarations in the rules deck.

Authorization requires full, trimmed, case-insensitive agreement on `mandate_id`, `service_id`, positive integer `cap_token`, `payload_hash`, and `sandbox_class`. A mandate is eligible only when its `state` equals `ELIGIBLE_STATE`. An audit is eligible only when `verdict_code` equals `REASON_1`, `REASON_2`, or `REASON_3`, case-insensitively. Preserve audit input order and consume each mandate row at most once. When several unused rows qualify, choose the greatest numeric 14-digit `recv_ts`; if timestamps tie, choose the earliest mandate input row.

Write `/app/out/mandate_report.csv` with this exact pipe-delimited header:

`claim_id|mandate_id|service_id|audit_class|sandbox_class|cap_token|verdict_code|status`

`audit_class` echoes the audit row's `sandbox_class`. For `AUTHORIZED`, emit the selected mandate's canonical `sandbox_class`; for `DENIED`, emit a blank `sandbox_class`. Status is exactly `AUTHORIZED` or `DENIED`.

Write `/app/out/mandate_summary.txt` as exactly four `key=value` lines: `authorized_count`, `authorized_mandates`, `denied_count`, and `denied_mandates`. The two mandate totals sum the positive integer `cap_token` values from the audit rows in their respective status groups.

Do not apply `/app/config/sandbox_windows.psv` yet.
