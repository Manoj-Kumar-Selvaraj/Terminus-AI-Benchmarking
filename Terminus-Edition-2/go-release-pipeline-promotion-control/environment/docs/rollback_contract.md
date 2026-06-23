# Rollback contract

Rollback is invoked with `go run ./cmd/pipelinesim rollback --history PATH --env ENV --out DIR [--target-build BUILD]`. Rollback redeploys an artifact already present in release history. It must not rebuild from the current branch tip or from `HEAD`.

Only records with `promotion_status` equal to `promoted` are eligible. Default rollback skips all other statuses, excludes the most recent promoted record for the requested environment, then chooses the latest promoted record that remains. An explicit `--target-build` is valid only when that build is a promoted record in the requested environment; wrong-environment, absent, and non-promoted targets fail closed.

Rollback must also enforce the compatibility floor in
`/app/config/pipeline_policy.json` at
`rollback.minimum_release_contract_by_env`. Only promoted records are subject
to compatibility filtering. A promoted record is rollback-eligible only when its
`release_contract_version` is present, well formed in `YYYY.MM` form, and
greater than or equal to the floor for the requested environment. Non-promoted
records (`failed`, `pending`, and similar) are skipped during selection and
must not invalidate the history file when they omit or malform
`release_contract_version`. Incompatible promoted records are excluded before
default rollback removes the most recent eligible promoted record. Explicit
targets that are below the environment floor fail closed.

Successful rollback manifests use `rollback_source: "release_history"` and
include `command_interface` with the stable CLI contract text
`pipelinesim rollback --history PATH --env ENV --out DIR [--target-build BUILD]`.
The `artifact_hash` value comes from the selected release record's
`artifact_hash`; `promoted_artifact_hash` comes from its separate
`promoted_artifact_hash` field. The two fields are independent and may differ.
