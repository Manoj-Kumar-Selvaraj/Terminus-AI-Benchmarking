# Handler contract

The production Lambda handler entry point is `/app/handler/index.mjs`. The offline simulator invokes it through `/app/handler/invoke.mjs`, which reads an event from stdin and writes the handler response to stdout.

The handler accepts events with `Records`, where each record contains `messageId`, `body`, `eventSourceARN`, and SQS attributes. Ledger side effects are JSON rows with `business_event_id`, `message_id`, account data, amount, operation, and status. Poison or malformed records must be represented through partial batch item failures instead of forcing successful peer records to retry.

The handler reads and writes the side-effect ledger at the path in `SIDE_EFFECT_LEDGER` (default `/app/data/side_effect_ledger.json`). When duplicate deliveries share the same `business_event_id`, the handler must not append a second committed row; it must record alternate SQS `message_id` values on the existing row in `duplicate_message_ids`.
