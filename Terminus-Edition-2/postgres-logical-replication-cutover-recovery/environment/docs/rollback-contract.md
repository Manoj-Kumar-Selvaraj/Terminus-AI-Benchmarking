# Rollback contract

Before target activation, rollback may abandon the attempt and reopen the source. After target activation, target writes are fenced, captured by their stable transaction identities, reverse-applied to the source exactly once, validated, and only then is the source reopened. Transactions already accepted by the source are not replayed from the subscription history.

A rollback operation ID is stable. Retrying the completed operation is a no-op that returns the stored result; a different operation ID for the same cutover is rejected.
