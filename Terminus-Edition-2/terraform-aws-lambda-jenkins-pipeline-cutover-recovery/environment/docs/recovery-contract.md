# Restart and Reconciliation Contract

Application checkpoints, request envelopes, deployment snapshots, cutover state, and the operation journal survive process restart.

## Durable state locations

| Artifact | Path |
|----------|------|
| Operation journal | `/app/state/operations.journal.jsonl` |
| Execution checkpoint | `/app/state/checkpoints/<execution_id>.json` |
| Saved deployment | `/app/state/deployments/<generation>.json` |
| Cutover state | `/app/state/cutover.json` |

The operation journal is JSON Lines at `/app/state/operations.journal.jsonl`. Each externally visible side effect is bracketed by `STARTED` and `COMMITTED` records that share one stable `operation_id`. A partially written final line may be discarded, but valid preceding records must be retained. Reconciliation must be repeatable.

The trusted runtime can report deployment drift for the active generation. Reconciliation reapplies the saved deployment and clears only confirmed drift. It must not delete unrelated runtime state.

Pending executions are resumed from their checkpoints. The same execution generation and operation identities are preserved. A stale worker may not change the generation already registered for an execution.

## `pipelinectl reconcile` output

`pipelinectl reconcile` prints one JSON object on stdout:

```json
{
  "journal_repaired": false,
  "drift_repaired": false,
  "resumed": []
}
```

| Field | Type | Meaning |
|-------|------|---------|
| `journal_repaired` | bool | `true` when an incomplete final JSONL record was discarded and the journal was rewritten from valid preceding lines |
| `drift_repaired` | bool | `true` when confirmed active-generation drift was cleared by reapplying the saved deployment snapshot |
| `resumed` | string[] | execution IDs that were resumed from durable checkpoints during this reconciliation pass |

Repeated reconciliation on a healthy system returns `journal_repaired: false`, `drift_repaired: false`, and `resumed: []`.
