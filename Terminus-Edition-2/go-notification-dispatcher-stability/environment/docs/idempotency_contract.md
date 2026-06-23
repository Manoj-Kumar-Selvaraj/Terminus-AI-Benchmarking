# Idempotent Retry Contract

Each notification has a stable `OperationKey` identifying one logical tenant-visible side effect.
Webhook endpoints support the standard `Idempotency-Key` request header.

`Client.DeliverWithRetry` must provide these guarantees:

- Every HTTP attempt carries `Idempotency-Key: <OperationKey>`.
- A transient 5xx response may be retried up to `MaxRetries` additional times.
- A non-transient 4xx response is returned immediately and is not retried.
- Concurrent calls for the same operation key share one in-flight retry sequence and receive the same terminal result.
- Successful operation keys are remembered; later calls return success without another HTTP request.
- A terminal failure is not remembered as successful, so a later independent call can try again.
- Different operation keys remain independent and may be delivered concurrently.

The local ledger coordinates process-local callers. The stable request header lets the upstream endpoint suppress a duplicated side effect when a response is lost or a transient response is returned after commit.
