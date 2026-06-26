# Pipeline Event Compatibility Contract

## Protocol version 1

Version 1 is emitted by the Jenkins bridge during rollout. It contains:

```text
protocol_version
execution_id
batch_id
artifact_digest
items
metadata
```

The migration derives the legacy owner using this exact schema:

```text
legacy-jenkins/<batch_id>
```

For example, batch `batch-42` has owner `legacy-jenkins/batch-42`. Existing valid version 1 events must continue to run.

## Protocol version 2

Version 2 adds an explicit workload owner:

```text
protocol_version
execution_id
batch_id
artifact_digest
owner
items
metadata
```

The owner is required for version 2. An execution ID cannot be reused with another batch, owner, or artifact digest. Item IDs must be non-empty and unique. Unsupported protocol versions are rejected before any Lambda stage is invoked.

## Checkpoint compatibility

The checkpoint returned by `pipelinectl run` and `pipelinectl resume` preserves the accepted request's `protocol_version` and `owner`. Version 1 checkpoints use `protocol_version: 1` and owner `legacy-jenkins/<batch_id>`. Version 2 checkpoints use `protocol_version: 2` and the explicit request owner. Checkpoints also carry `epoch` and `generation` pinned for the execution lifetime.
