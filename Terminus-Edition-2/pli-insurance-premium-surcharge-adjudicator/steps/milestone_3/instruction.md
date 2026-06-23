Apply fiscal-window eligibility from `/app/config/fiscal_windows.psv`, whose columns are `account_no|open_ts|close_ts|state`.

A window applies only to the same `account_no` and when its state equals `OPEN_FISCAL_STATE` from `/app/src/premium_rules.pli`, case-insensitively. Policy `ingest_ts`, adjustment `adj_ts`, window `open_ts`, and window `close_ts` must be numeric 14-digit UTC values. Both policy and adjustment timestamps must be inside the same inclusive window, and `ingest_ts` must not be later than `adj_ts`. Missing, malformed, closed, wrong-account, or non-covering windows are ineligible.

Preserve full-key matching, aliases, policy and opcode gates, one-time row consumption, adjustment order, latest-ingest candidate selection, pipe-separated report schema, canonical valid risk codes, blank invalid risk codes, and summary totals.
