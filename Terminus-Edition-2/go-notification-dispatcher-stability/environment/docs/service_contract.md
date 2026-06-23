# Billing Alert Notification Service

The service accepts billing-alert jobs and posts them to tenant webhook endpoints through a bounded worker pool. Each job carries a stable operation key, client identifier, target URL, event type, and payload fields.

Operational guarantees:

- producers make progress under a bounded backlog without lock/channel inversion;
- rolling shutdown cancels in-flight work and rejects new jobs without panics;
- transient retry sequences are idempotent per operation key while unrelated operations remain concurrent;
- legacy and modern clients retain their published JSON schemas on every attempt.

The task is an incident-recovery exercise. Do not replace the service with a fixture-specific program or remove the existing exported APIs.
