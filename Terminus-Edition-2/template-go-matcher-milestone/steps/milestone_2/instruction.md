Extend `/app/cmd/reconcile/main.go` while preserving every milestone 1 rule.

Normalize legacy tier aliases after trimming and case folding: `TA`→`TIER_A`, `TB`→`TIER_B`. Unknown normalized tiers stay ineligible. Matched rows emit canonical tiers; unmatched rows leave `tier` blank. Preserve adjustment input order, report schema, status labels, and summary keys.

Compile with `/usr/local/go/bin/go`.
