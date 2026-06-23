# Tie-break note

When duplicate expected snapshots exist for one field, the matcher must prefer the latest `recv_ts`, then the earliest catalog row. Stale snapshots must not steal consumption from fresher rows.
