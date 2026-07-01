# Plugin resolution contract

Plugin recovery must resolve compatibility from offline contracts. Do not hardcode plugin names, plugin versions, dependency names, or fixture-specific answers.

Use these files as the source of truth:

- `config/version_contract.json`
- `config/plugin_catalog.json`

Compute the transitive dependency closure for every essential plugin required by the selected Jenkins target. Choose the lowest catalog version that satisfies all of these constraints:

- The required minimum plugin version.
- The selected target Jenkins core version.
- The resolved Java runtime.
- Every declared dependency minimum.

Tie-breaking must be deterministic. Dependency cycles and missing compatible candidates must be detected before any state change.

`plan --json` is read-only, but it must fully validate plugin resolution for the requested recovery scope. Missing compatible candidates and dependency cycles must make `plan --json`, `apply`, and `resume` exit non-zero before cumulative mutation.

Plugin plans must report the resolved plugin/version map on the relevant action object as `actions[].resolved`. Do not report the plugin closure only as top-level metadata.

`apply` and `resume` must enable required plugins and upgrade only resolver-selected entries. Preserve optional plugins, unrelated plugins, and unknown plugin inventory metadata.

Strict stderr substrings:

- Missing candidate: `no compatible plugin candidate for <plugin>`
- Dependency cycle: `dependency cycle`

The `before_plugins_commit` fault point exits non-zero before plugin inventory mutation. The `after_plugins_commit_response_lost` fault point exits non-zero after a durable plugin commit. Resuming with the same owner must not perform a second commit. Successful plugin recovery emits exactly one `plugins_committed` event.