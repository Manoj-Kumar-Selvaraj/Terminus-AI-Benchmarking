# Versioned Cutover and Jenkins Overlap Contract

Each execution pins one deployed Lambda generation when it begins. Alias changes affect only new executions. An in-flight generation remains available until its pinned work completes.

Only one implementation may produce settlement side effects for a batch. During Lambda-primary operation, the Jenkins bridge runs in observation-only shadow mode. It may compare stage results but must not write ledger, report, notification, or archive effects.

A cutover response can be lost after the trusted control plane commits the alias change. Retrying or reconciling must discover the committed generation. Rollback chooses a generation for future work without rewriting checkpoints belonging to already-running executions.

## Cutover command output

`pipelinectl cutover` and `pipelinectl rollback` print one JSON object on stdout:

```text
active_generation
previous_generation
writer
epoch
```

`epoch` must match the trusted runtime epoch after the transition commits. When a control-plane response is lost after the alias change, a retry or reconciliation pass must return the committed `active_generation` and `epoch` from authoritative runtime state rather than duplicating or reversing the transition.
