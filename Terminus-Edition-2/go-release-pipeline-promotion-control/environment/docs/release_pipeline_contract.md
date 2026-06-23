# Release pipeline contract

The offline simulator models the Jenkins release pipeline without requiring a Jenkins controller. The public command is `go run ./cmd/pipelinesim run --scenario PATH --out DIR`. Existing stage names must remain: Build, Unit Test, Integration Test, Package, Quality Gate, Promote, Rollback. Release manifests retain the ordered pipeline stages `Build`, `Unit Test`, `Integration Test`, `Package`, `Quality Gate`, and `Promote`. The simulator must preserve `build_number`, `commit_sha`, `artifact_hash`, and `promoted_artifact_hash` through every persisted manifest.
