# Audit Support

Auditors expect all committed closing groups to appear exactly once in `/app/out/escrow_commit_ledger.csv`. Held groups must not consume trust funds. Repeated reruns after an ABEND must be idempotent.
