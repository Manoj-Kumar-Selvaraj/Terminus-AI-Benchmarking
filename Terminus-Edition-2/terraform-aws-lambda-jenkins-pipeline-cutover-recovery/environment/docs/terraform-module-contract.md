# Terraform Lambda Module Contract

The migration uses the public module source and pinned task fixture version:

```hcl
source  = "terraform-aws-modules/lambda/aws"
version = "7.20.1"
```

The module is instantiated once per stage through `for_each`. Each function is a Go custom-runtime package using `provided.al2023`, handler `bootstrap`, a unique package hash, published immutable versions, and a `live` alias. Step Functions may invoke only the versioned alias. Current-version trigger creation must remain disabled so `$LATEST` is never granted as a parallel execution path.

The task simulator implements the subset of module behavior used by this repository. It does not contact AWS or the Terraform registry.

Each stage must retain its documented timeout, memory, reserved concurrency, and least-privilege action set from `/app/infra/stages.json`. Wildcard principals, wildcard actions, shared unversioned package hashes, and a single shared function name are incompatible with the migration contract.

## Normative per-stage contract

The following values are exact. A deployment with a different timeout, memory size, reserved concurrency, or action set must be rejected before registration with the trusted runtime.

| Stage | Timeout | Memory | Reserved concurrency | Allowed actions |
|---|---:|---:|---:|---|
| `intake` | 30 | 256 | 4 | `logs:PutLogEvents`, `xray:PutTraceSegments` |
| `verify_manifest` | 45 | 256 | 4 | `s3:GetObject`, `kms:Verify`, `logs:PutLogEvents` |
| `acquire_lock` | 20 | 128 | 8 | `dynamodb:PutItem`, `dynamodb:GetItem`, `logs:PutLogEvents` |
| `fetch_inputs` | 120 | 512 | 12 | `s3:GetObject`, `logs:PutLogEvents` |
| `validate_inputs` | 90 | 512 | 12 | `s3:GetObject`, `logs:PutLogEvents` |
| `transform_records` | 180 | 1024 | 8 | `s3:GetObject`, `s3:PutObject`, `logs:PutLogEvents` |
| `precheck_ledger` | 60 | 256 | 6 | `dynamodb:GetItem`, `logs:PutLogEvents` |
| `write_ledger` | 120 | 512 | 6 | `dynamodb:PutItem`, `dynamodb:UpdateItem`, `logs:PutLogEvents` |
| `build_report` | 90 | 512 | 4 | `s3:PutObject`, `logs:PutLogEvents` |
| `notify_partner` | 30 | 256 | 4 | `events:PutEvents`, `logs:PutLogEvents` |
| `archive_batch` | 60 | 256 | 4 | `s3:GetObject`, `s3:PutObject`, `s3:DeleteObject`, `logs:PutLogEvents` |
| `release_lock` | 20 | 128 | 8 | `dynamodb:DeleteItem`, `logs:PutLogEvents` |
