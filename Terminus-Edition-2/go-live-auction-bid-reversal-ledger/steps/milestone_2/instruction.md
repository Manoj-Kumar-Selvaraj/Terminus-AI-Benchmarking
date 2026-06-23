Extend `/app/cmd/reconcile/main.go` for legacy channel aliases while preserving every milestone 1 matching, window, consumption, report, and summary rule.

Add static aliases after trimming and case folding: `WEB`→`ONLINE`, `APP`→`MOBILE`, `FLOOR`→`ONSITE`. Unknown normalized channels stay ineligible even when bid and reversal agree. Matched rows emit canonical `ONLINE`, `MOBILE`, or `ONSITE`; unmatched rows leave `channel` blank. Preserve reversal input order, report schema, status labels, reversal amount text, and summary keys.

Compile with `/usr/local/go/bin/go`.
