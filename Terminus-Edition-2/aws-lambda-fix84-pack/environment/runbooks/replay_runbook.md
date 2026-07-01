# Replay and restart recovery notes

The local replay command may be stopped and invoked again with the same ledger, DLQ, and delivery checkpoint paths. Receive counts continue across processes. At `max_receive_count`, poison and malformed records are appended to the DLQ exactly once and are no longer delivered.

DLQ rows preserve `original_message_id`, `business_event_id` when decodable, `source_queue_arn`, `receive_count`, and a stable reason. The supplied poison fixture uses `schema_missing_amount`; malformed JSON uses `MALFORMED_JSON`.

A source message already represented in a pre-existing DLQ file is retired even if the prior process exited before writing its delivery checkpoint.
