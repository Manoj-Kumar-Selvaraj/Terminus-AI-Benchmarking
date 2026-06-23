# Incident Timeline — Billing Alert Surge

| Time (UTC) | Event |
|---|---|
| 21:04 | Statement completion doubles outbound alert volume. |
| 21:07 | Producers stop making progress while all four workers remain allocated. |
| 21:11 | A goroutine dump shows queue senders and workers waiting on the same lock. |
| 21:18 | Backlog remediation exposes shutdowns exceeding the 250 ms deployment window. |
| 21:24 | A transient 503 after upstream commit creates repeated retry sequences for one operation key. |
| 21:31 | The on-prem legacy adapter rejects the second attempt because its body changed to the modern schema. |

Each milestone addresses the next failure exposed in the same dispatch and delivery path.
