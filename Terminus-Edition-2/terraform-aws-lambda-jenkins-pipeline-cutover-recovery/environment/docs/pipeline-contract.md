# Settlement Pipeline Runtime Contract

`settlement-release-pipeline` replaces a Jenkins controller job that processed bank settlement batches through twelve ordered stages:

1. `intake`
2. `verify_manifest`
3. `acquire_lock`
4. `fetch_inputs`
5. `validate_inputs`
6. `transform_records`
7. `precheck_ledger`
8. `write_ledger`
9. `build_report`
10. `notify_partner`
11. `archive_batch`
12. `release_lock`

Every accepted execution carries one immutable `execution_id`, `batch_id`, artifact digest, owner, protocol version, metadata map, and one or more item records. Stage outputs must preserve the execution identity, batch identity, artifact digest, selected deployment generation, and item identity where applicable.

The public CLI is `/app/bin/pipelinectl` and must preserve these commands:

```text
pipelinectl deploy --infra <directory>
pipelinectl run --request <json-file>
pipelinectl resume --execution <execution-id>
pipelinectl cutover --generation <n> --writer lambda
pipelinectl rollback --generation <n>
pipelinectl jenkins-shadow --request <json-file>
pipelinectl reconcile
pipelinectl inspect --what cutover|execution|runtime [--execution <id>]
```

The implementation must invoke the trusted runtime for deployment and stage side effects. It must not write `/var/lib/lambda-pipeline-runtime/state.json` directly.

## Command output schemas

`pipelinectl run` and `pipelinectl resume` return the durable checkpoint JSON documented in `/app/docs/retry-idempotency-contract.md`, including `protocol_version`, `owner`, `generation`, `epoch`, `next_stage`, and `status`.

`pipelinectl cutover` and `pipelinectl rollback` return cutover state JSON documented in `/app/docs/cutover-contract.md`, including `active_generation`, `previous_generation`, `writer`, and `epoch`.

`pipelinectl reconcile` returns the reconciliation summary JSON documented in `/app/docs/recovery-contract.md`:

```text
journal_repaired
drift_repaired
resumed
```
