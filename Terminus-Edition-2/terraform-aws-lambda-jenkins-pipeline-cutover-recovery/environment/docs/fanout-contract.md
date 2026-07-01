# Fan-out and Partial Failure Contract

The item stages are `fetch_inputs`, `validate_inputs`, `transform_records`, `precheck_ledger`, and `write_ledger`.

One permanently invalid item is isolated only after exactly three `validate_inputs` attempts and recorded in the batch DLQ. The trusted runtime's `dlq` inspection is a JSON object keyed by `batch_id`; every value is the sorted array of isolated item IDs for that batch. Valid sibling items continue through ledger write. The batch finishes as `PARTIAL`; an all-valid batch finishes as `SUCCEEDED`.

A batch identity is owned by one execution. A second execution cannot process the same batch even after the first execution releases its transient lock. Unrelated batches must remain independent and may progress concurrently.

Both successful and partial completion must release the transient runtime lock. Durable batch ownership remains recorded separately, so releasing the transient lock does not allow a second execution to claim the same batch.
