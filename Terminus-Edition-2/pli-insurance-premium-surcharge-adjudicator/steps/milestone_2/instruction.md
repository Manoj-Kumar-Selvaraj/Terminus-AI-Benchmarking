Extend risk-code comparison with the `ALIAS_*` declarations in `/app/src/premium_rules.pli`. Each declaration has the form `raw=>canonical`.

Trim and case-fold alias keys and both policy and adjustment `risk_code` values **for comparison only**. The right-hand canonical token in each alias declaration keeps its trimmed, declared spelling in valid report output; for example, `f=>FeD` emits `FeD`, not `FED` or `fed`. Unknown values do not match a different canonical value. Valid report rows emit that canonical risk code; invalid rows keep `risk_code` blank.

Preserve full-key matching, policy eligibility, opcode eligibility, one-time row consumption, adjustment order, candidate selection, pipe-separated report schema, and summary behavior. Fiscal windows remain out of scope.
