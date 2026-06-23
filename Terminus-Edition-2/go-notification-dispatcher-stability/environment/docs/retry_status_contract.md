# HTTP Retry Classification

- HTTP 2xx and 3xx responses are successful delivery outcomes.
- HTTP 4xx responses are terminal for the current call and must not be retried automatically.
- HTTP 5xx responses are transient and may be retried up to the configured limit.
- Caller cancellation terminates the retry sequence.
- Transport errors may be retried while the caller context remains active.
