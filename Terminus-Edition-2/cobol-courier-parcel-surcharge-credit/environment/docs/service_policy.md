# Service Policy

`/app/config/service_policy.csv` has the header:

`branch,service_tier,enabled,max_credit_cents,priority`

Branch and service tier are exact fixed-width business values after trimming.
Enabled is `Y` compared case-insensitively. Amount limits and priorities are
unsigned decimal integers. Malformed rows do not enable matching.
