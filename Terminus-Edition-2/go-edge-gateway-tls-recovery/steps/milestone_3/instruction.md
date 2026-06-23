The rotation entered its supported overlap window, with retiring and replacement ledger instances active at the same time. Review `/app/evidence/overlap_validation.log`, `/app/docs/overlap_contract.md`, and `/app/internal/tlsmaterial/manager.go`. A gateway created from the rotation bundle must authenticate either issuer population regardless of certificate order in that PEM file.

Preserve the earlier trust-path and routed-identity guarantees. During overlap rollout, operations may replace the configured `RootCAFile` contents in place and call `Manager.Reload()` so the gateway reloads the expanded trust bundle without restarting. A failed trust reload must return an error and leave the prior trust anchors active. Do not hard-code the repository bundle, depend on the host trust store, or weaken hostname verification.

Success is verified by the milestone Go tests under `/app/internal/tlsmaterial` passing with `go test -race`.
