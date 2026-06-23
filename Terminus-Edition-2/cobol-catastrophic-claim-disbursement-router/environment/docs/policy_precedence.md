# Policy and review precedence

Reject reason precedence is stored in `/app/config/reject_precedence.psv`. Manual-review
reason precedence is stored in `/app/config/review_reason_precedence.psv`. The policy deck
`/app/config/payment_policy.pli` supplies payment thresholds using PL/I-style declarations.
Do not replace these files with hardcoded constants in the program; tests rewrite them.
