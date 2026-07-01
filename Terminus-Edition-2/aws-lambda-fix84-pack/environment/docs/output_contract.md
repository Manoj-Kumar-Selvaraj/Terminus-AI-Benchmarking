# Simulator output contract

`/app/scripts/run_simulation.py` writes JSON probe results for the offline replay harness. Field names below are normative for verifier expectations.

## Mapping probe (`--scenario mapping`)

Reports the active event-source mapping derived from `/app/config/event_source_mapping.json` and `/app/config/queues.json`.

| Field | Type | Meaning |
| --- | --- | --- |
| `uuid` | string | Mapping identifier from config |
| `enabled` | boolean | Whether the mapping is enabled |
| `active` | boolean | `true` only when enabled and `event_source_arn` equals `expected_active_queue_arn` |
| `function_name` | string | Lambda function target, e.g. `payments-ledger-ingestor:live` |
| `event_source_arn` | string | Configured queue ARN on the mapping |
| `expected_event_source_arn` | string | Migrated queue ARN from `queues.json` |
| `old_queue_arn` | string | Historical queue ARN that must not feed active processing |
| `batch_size` | integer | Configured maximum batch size; the live contract uses `3` |
| `function_response_types` | list[string] | Must include `ReportBatchItemFailures` |

## IAM probe (`--scenario iam`)

Reports IAM decisions for the migrated queue using `/app/config/lambda_role_policy.json`.

| Field | Type | Meaning |
| --- | --- | --- |
| `queue_arn` | string | Migrated queue ARN under test |
| `decisions` | object | Map of required SQS actions to `allowed` or `denied` |
| `old_queue_receive` | string | Decision for `sqs:ReceiveMessage` on the old queue ARN |
| `has_broad_sqs_grant` | boolean | `true` when wildcard SQS action or resource grants exist |
| `has_log_permissions` | boolean | `true` when CloudWatch Logs permissions remain present |

Required SQS actions in `decisions`:

- `sqs:ReceiveMessage`
- `sqs:DeleteMessage`
- `sqs:ChangeMessageVisibility`
- `sqs:GetQueueAttributes`

## Batch probe (`--scenario batch`)

Reports deterministic offline replay for one SQS batch file.

| Field | Type | Meaning |
| --- | --- | --- |
| `mapping` | object | Mapping probe snapshot for the current config |
| `queue_arn` | string | Queue ARN from the batch fixture |
| `cycles` | list[object] | Per-cycle delivered/failed/deleted message IDs |
| `access_denied` | boolean | `true` when required queue actions are denied |
| `access_denied_actions` | list[string] | Denied SQS actions, if any |
| `delivered_message_ids` | list[string] | Message IDs delivered to the handler |
| `deleted_message_ids` | list[string] | Successfully processed message IDs removed from the queue |
| `failed_message_ids` | list[string] | Message IDs returned through partial batch failures |
| `receive_counts` | object | Map of message ID to receive count after replay |
| `dlq_message_ids` | list[string] | Message IDs routed to the DLQ |
| `ledger_entries` | list[object] | Committed side-effect ledger rows after replay |
| `dlq_entries` | list[object] | DLQ rows after replay |

Batch simulations report delivered, deleted, failed, receive-count, ledger, and DLQ state after deterministic offline replay.
