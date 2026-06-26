# Cutover rehearsal timeline

* 09:12 — initial copy is declared complete at `0/500`.
* 09:18 — publication repair reports success; slot identity changes in one dry run.
* 09:24 — validation sees preferences and deleted contact methods diverge despite low lag.
* 09:41 — after coverage is adjusted, a profile transaction stops at a nullable preference field and leaves its parent visible.
* 10:03 — sequence-backed insert on the target collides with an already replicated identifier.
* 10:17 — two readiness components report different fence positions after a source write.
* 10:31 — cutover failure injection leaves both application writer endpoints enabled.
* 10:48 — rollback replays an old-source transaction and duplicates an audit event.
* 11:02 — controller restart cannot identify the durable phase or exact recovery LSN.
