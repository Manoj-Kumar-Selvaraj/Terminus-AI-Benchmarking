# Incident timeline: FNBULKUP bulk update drift

2026-06-16 22:15 IST — Branch Operations loaded the first consolidated financial-master bulk update after the DB2 package refresh.

2026-06-16 22:41 IST — FNBULKUP reported an ABEND on a missing master row even though the runbook says missing rows must be business rejects and the rest of the file can continue.

2026-06-17 00:10 IST — A rerun after the ABEND showed duplicate ledger/audit rows for records that had already committed before the restart marker.

2026-06-17 01:20 IST — During online posting overlap, one account returned SQLCODE -911. The batch log looked green, but the locked update vanished and the checkpoint advanced past it.

2026-06-17 03:05 IST — Credit-limit records exposed master/risk drift: master limit changed even when the related risk row rejected the update.

The task is to repair the offline simulator-backed FNBULKUP workflow without real DB2 credentials.
