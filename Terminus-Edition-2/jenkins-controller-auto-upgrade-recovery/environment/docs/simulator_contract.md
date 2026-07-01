# Offline Jenkins simulator and recovery-controller contract

The compiled simulator diagnoses persisted state under `APP_ROOT`. It does not repair state. Default `APP_ROOT` is `/app`, and recovery must pass the active `APP_ROOT` to the simulator child process.

Use:

```bash
/app/scripts/jenkins_cluster_sim diagnose --json
/app/scripts/jenkins_cluster_sim start
```

`start` writes `out/controller_diagnostics.json` on every attempt and writes `out/controller_status.json` only when the phase is `READY`. `diagnose --json` prints diagnostics and does not create outputs.

`verify --json` in `/app/scripts/jenkins-recover` is a read-only wrapper around simulator diagnostics. It must invoke the simulator binary from `JENKINS_SIM_BIN` when that environment variable is set, otherwise fall back to `/app/scripts/jenkins_cluster_sim`. The child process must receive `APP_ROOT` for the active incident root. `verify` must not run `start`, must not write `/app/out`, and must return the simulator diagnostic exit code: `0` only when `ready` is true, non-zero for partial progress.

Final full recovery must invoke the same simulator binary's `start` subcommand after all durable phases complete. Do not hand-write `out/controller_diagnostics.json` or `out/controller_status.json`.

The participant must implement `/app/recovery/main.go`, invoked through:

```bash
/app/scripts/jenkins-recover inspect --json
/app/scripts/jenkins-recover plan --json
/app/scripts/jenkins-recover apply --owner OWNER [--fault POINT] [--hold-ms MS]
/app/scripts/jenkins-recover resume --owner OWNER [--fault POINT] [--hold-ms MS]
/app/scripts/jenkins-recover verify --json
```

`plan --json` is read-only, but it must validate the requested recovery scope. That includes missing selected targets, missing compatible backups, plugin resolver failures, dependency cycles, policy guard readiness, and missing eligible cluster controllers when those phases are in scope.

`apply` and `resume` use durable journal and lease state under `recovery_state/`. Tests point the same implementation at fresh and dynamically modified incident roots through `APP_ROOT`; fixture-specific final-state edits are insufficient.

The `--owner` value is part of the offline exercise interface. The prefix before the first hyphen selects the recovery boundary for `apply` and `resume`: `operator-*` stops after runtime recovery, `restore-*` stops after home recovery, `plugins-*` stops after plugin recovery, `policy-*` stops after upgrade-policy recovery, and `cluster-*` or an unrecognized prefix runs the full controller recovery. A boundary-scoped apply must leave later simulator phases unrepaired, so `verify --json` still returns non-zero until full recovery reaches READY.

The simulator phases remain cumulative: runtime, home, plugins, upgrade policy, cluster fencing, then READY.

Public JSON contracts:

- `plan --json` returns an object with `operation_id` and an `actions` array. When runtime recovery is required, the first action is the runtime action and includes `target_version` and `required_java`. Home-recovery plans include top-level `selected_snapshot` as a plain snapshot ID string. Plugin plans must include the resolved plugin/version map on the relevant action object as `actions[].resolved`; do not report the plugin closure only as top-level metadata. Policy plans include `guards` as an array of plain strings such as `java_preflight`, `verified_backup`, and `owner_lease`, not structured guard objects. Final cluster plans include top-level `elected_controller` as the chosen controller pod name string.
- `inspect --json` returns `operation_id`, `milestone`, `journal_records`, and a `lease` object. `milestone` is the current recovery phase label. `journal_records` is an integer count of journal lines, not an array. The lease object contains `operation_id`, `owner`, integer `generation`, and `status`.
- `verify --json` and `jenkins_cluster_sim diagnose --json` return `phase`, boolean `ready`, `checks`, and `errors`. Each check object has at least `name` and boolean `ok`, plus phase-specific diagnostic fields.
- `out/controller_diagnostics.json` uses the same diagnostic schema as `diagnose --json`.
- `out/controller_status.json` is written only after READY and contains `status`, `cluster`, `deployment`, `jenkins_version`, `java_major`, `home_claim`, and may include additional simulator metadata such as `timestamp`.

Stable CLI error substrings used by verifiers:

- Unknown selected Jenkins target: `absent from version contract`
- Active operation owned by another recovery owner: `fenced by owner <owner>`
- No complete compatible backup can be selected: `no complete compatible backup`
- No plugin candidate satisfies a contract: `no compatible plugin candidate for <plugin>`
- Plugin dependency cycle: `dependency cycle`
- Concurrent process lock: `local lock`
- No eligible cluster controller: `no eligible controller`