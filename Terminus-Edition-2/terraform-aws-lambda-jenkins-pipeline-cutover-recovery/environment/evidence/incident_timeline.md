# Incident Timeline — 23 June 2026

- 20:00 UTC — Terraform apply for the Lambda migration completed with no provider error.
- 20:04 UTC — The first batch failed before the fourth Jenkins-equivalent stage; only part of the expected function fleet appeared in the deployment inventory.
- 20:11 UTC — Operators corrected the visible invocation failure. New batches reached ledger publication.
- 20:18 UTC — A Lambda timeout caused the entire batch to restart and duplicate two ledger effects and one partner notification.
- 20:27 UTC — A malformed item repeatedly blocked valid sibling items. Queue age increased while unrelated batches intermittently progressed.
- 20:43 UTC — The `live` alias moved during an in-flight execution. One execution reported stages from two function versions.
- 20:46 UTC — Jenkins shadow verification produced a second archive event for the same batch.
- 21:03 UTC — The migration controller restarted after an alias response timeout. The local checkpoint and trusted control-plane state disagreed.
- 21:12 UTC — A second Terraform apply reported no configuration change, but the active simulated deployment remained drifted.
