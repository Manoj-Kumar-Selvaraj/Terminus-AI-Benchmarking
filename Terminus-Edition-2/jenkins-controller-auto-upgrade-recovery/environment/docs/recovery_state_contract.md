# Recovery state contract

Recovery-owned state lives under `recovery_state/`.

- `journal.jsonl` contains complete JSON records with exact snake_case field names, including `event`, `operation_id`, `owner`, and `milestone`; do not emit camelCase or PascalCase alternatives.
- `lease.json` contains `operation_id`, `owner`, integer `generation`, and `status`.
- `staging/` may contain validated but not yet activated home data.
- A local process lock, such as `process.lock`, must live under `recovery_state/`.

Committed events must not be repeated after a lost response. An active operation is fenced to its owner. The local process lock prevents concurrent mutation of the same incident root. A completed operation is a strict no-op on replay.

Before the first mutation, validate the complete cumulative plan for the requested scope. Preflight failures such as an unknown target, no compatible backup, plugin resolver failure, dependency cycle, or no eligible controller must fail before partial writes.

## Operation identity

`operation_id` is deterministic for the incident and target. It must change when the deployment identity changes, such as cluster or deployment identity, or when the selected target Jenkins version changes.

## Lease schema

`lease.json` uses this shape:

```json
{
  "operation_id": "...",
  "owner": "operator-a",
  "generation": 1,
  "status": "active"
}
```

`generation` is a JSON integer. `status` is `active` while a lost-response or in-progress operation is resumable by the recorded owner, and `completed` once the operation has reached the final committed state.

A different owner must fail with stderr containing `fenced by owner <owner>` when lease fencing blocks it. Concurrent mutation may also fail with stderr containing `local lock` or `fenced`.

Write `recovery_state/lease.json` before any `--hold-ms` sleep so another process can observe the active operation.

## Journal event order

Journal records use the JSON field `event` for the recovery phase. Durable events are cumulative and must be recorded once in this order:

1. `runtime_committed`
2. `home_staged`
3. `home_committed`
4. `plugins_committed`
5. `preflight_completed`
6. `policy_committed`
7. `cluster_committed`
8. `operation_completed`

Recovery scopes emit only the events required by their boundary, followed by `operation_completed` for a successful operation. Full cluster recovery records exactly one `cluster_committed` before `operation_completed`.

`inspect --json` reports `operation_id`, `milestone`, `journal_records`, and `lease`. `milestone` is the current recovery phase label. `journal_records` is the integer number of records in `journal.jsonl`; it must not return the record array.

Completed replay must change no persistent state and append no journal events.

## Fault points

Fault points are stable public strings. They model lost responses or crashes. When a fault is triggered, the command must exit non-zero even if the affected phase commit was already written durably. Faults are not shortcuts for writing final output files.

| Recovery phase | Fault point | Required behavior |
|---|---|---|
| runtime | `before_runtime_commit` | Fail non-zero before deployment mutation and before journal commit |
| runtime | `after_runtime_commit_response_lost` | Exit non-zero after durable runtime commit; same owner resumes without a second `runtime_committed` |
| home | `after_home_stage` | Exit non-zero after durable staging; live home remains unchanged; same owner resumes and commits once |
| plugins | `before_plugins_commit` | Fail non-zero before plugin inventory mutation |
| plugins | `after_plugins_commit_response_lost` | Exit non-zero after durable plugin commit; same owner resumes without a second `plugins_committed` |
| policy | `after_policy_commit_response_lost` | Exit non-zero after durable policy commit; same owner resumes without a second `policy_committed` |
| cluster | `after_cluster_commit_response_lost` | Exit non-zero after durable cluster and queue commits; same owner resumes without a second `cluster_committed` |

## Local process lock and `--hold-ms`

The recovery controller must use a local lock file under `recovery_state/` so only one process mutates an incident root at a time.

For testable concurrency, `apply --hold-ms N` and `resume --hold-ms N` must hold the local lock for approximately `N` milliseconds after the lease has been written and before later mutations proceed.

A competing owner must fail with stderr containing either `local lock` or `fenced`.