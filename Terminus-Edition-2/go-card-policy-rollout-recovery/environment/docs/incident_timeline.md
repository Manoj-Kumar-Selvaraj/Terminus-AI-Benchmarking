# Incident timeline

- 21:02 UTC — emergency generation 184 is queued for three authorisation regions.
- 21:03 UTC — the deployment is terminated during a journal append. The next pod cannot render status from the shared volume.
- 21:11 UTC — an operator removes the visibly broken suffix and restarts. Delivery resumes.
- 21:13 UTC — the US gateway shows two delivery identities for one rollout after a worker dies immediately after the remote apply.
- 21:18 UTC — parallel workers are enabled to drain the backlog. A delayed generation 183 response arrives after generation 184 is active.
- 21:27 UTC — journal compaction is run to reduce replay time. The next restart shows previously completed deliveries as pending and accepts an older on-disk record from a rollback node inconsistently.

The four milestones follow this single recovery sequence. Do not erase the state directory, reset gateway state, disable concurrency, or remove the failpoints used to reproduce the incident.
