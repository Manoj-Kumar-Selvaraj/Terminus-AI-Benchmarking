# Ruby Subscription Seat Proration Ledger Support Note 1

This support note documents reconciliation edge cases used by operations: canonical value validation, timestamp ordering, window eligibility, release-calendar handling, seat-ledger capacity, and deterministic output schemas.

Operations note: kind aliases, policy rows, release dates, and seat-ledger capacity are runtime configuration. Reconciliation runs must use the shipped files instead of embedding the sample values.
