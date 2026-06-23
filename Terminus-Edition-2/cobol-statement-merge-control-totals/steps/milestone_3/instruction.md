With milestones 1 and 2 addressed, the merge still assigns committed totals to the wrong account when a sort run ends and the next run opens. The incident log shows a closing `ACCT1001` group posted against the first account read from the next stream.

Fix file-transition commits so each pending `(account_id, stmt_date)` group is written under its own keys before the next run is processed. Preserve prior milestone behavior and documented output layouts.
