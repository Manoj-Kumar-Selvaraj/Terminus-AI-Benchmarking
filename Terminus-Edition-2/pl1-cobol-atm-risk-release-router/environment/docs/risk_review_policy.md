# Risk review policy

Automatic release is permitted only when the matched hold is eligible, the terminal trust tier allows it, the card is not flagged for mandatory review, and applying the release would not exceed same-day count or amount thresholds. Review reasons use the configured precedence from `/app/config/review_reason_precedence.psv`.

Supervisor approvals are supplied in `/app/data/supervisor_approvals.psv`. An approved review can be committed during the final processing stage. Denied or missing approvals remain in review and must not update exposure.
