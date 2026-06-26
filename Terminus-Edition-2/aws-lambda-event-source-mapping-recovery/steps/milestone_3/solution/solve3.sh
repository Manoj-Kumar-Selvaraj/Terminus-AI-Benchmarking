#!/usr/bin/env bash
set -euo pipefail
python3 - <<'SOLVEPY'
import json
from pathlib import Path
mapping = Path('/app/config/event_source_mapping.json')
data = json.loads(mapping.read_text())
data['enabled'] = True
data['function_name'] = 'payments-ledger-ingestor:live'
data['event_source_arn'] = 'arn:aws:sqs:us-east-1:111122223333:payments-ledger-v2'
data['batch_size'] = 3
data['function_response_types'] = ['ReportBatchItemFailures']
data['maximum_batching_window_seconds'] = 2
data['scaling_config'] = {'maximum_concurrency': 4}
data['filter_criteria'] = {'event_type': ['ledger_credit']}
data['bisect_batch_on_function_error'] = False
mapping.write_text(json.dumps(data, indent=2) + '\n')
policy = {
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AllowRuntimeLogs",
      "Effect": "Allow",
      "Action": [
        "logs:CreateLogGroup",
        "logs:CreateLogStream",
        "logs:PutLogEvents"
      ],
      "Resource": "arn:aws:logs:us-east-1:111122223333:log-group:/aws/lambda/payments-ledger-ingestor:*"
    },
    {
      "Sid": "AllowMigratedQueuePolling",
      "Effect": "Allow",
      "Action": [
        "sqs:ReceiveMessage",
        "sqs:DeleteMessage",
        "sqs:ChangeMessageVisibility",
        "sqs:GetQueueAttributes"
      ],
      "Resource": "arn:aws:sqs:us-east-1:111122223333:payments-ledger-v2"
    }
  ]
}
Path('/app/config/lambda_role_policy.json').write_text(json.dumps(policy, indent=2) + '\n')
SOLVEPY

cat > /app/handler/index.mjs <<'HANDLER'
import { appendLedgerEntry } from "./lib/ledger.mjs";

class MessageFailure extends Error {
  constructor(reason) {
    super(reason);
    this.reason = reason;
  }
}

function decodeBody(record) {
  const body = record.body ?? "";
  try {
    if (typeof body === "string") {
      return JSON.parse(body);
    }
    if (typeof body === "object" && body !== null) {
      return body;
    }
  } catch {
    throw new MessageFailure("MALFORMED_JSON");
  }
  throw new MessageFailure("MALFORMED_JSON");
}

function processRecord(record) {
  const body = decodeBody(record);
  if (body.poison === true) {
    throw new MessageFailure(body.failure_reason || "POISON_MESSAGE");
  }
  const required = [
    "business_event_id",
    "account_id",
    "amount_cents",
    "currency",
    "operation",
  ];
  if (required.some((key) => !(key in body))) {
    throw new MessageFailure("SCHEMA_INVALID");
  }
  appendLedgerEntry({
    message_id: record.messageId,
    business_event_id: body.business_event_id,
    account_id: body.account_id,
    amount_cents: body.amount_cents,
    currency: body.currency,
    operation: body.operation,
    status: "COMMITTED",
  });
}

export async function handler(event) {
  const failures = [];
  for (const record of event.Records || []) {
    try {
      processRecord(record);
    } catch (err) {
      if (err instanceof MessageFailure) {
        failures.push({ itemIdentifier: record.messageId });
        continue;
      }
      throw err;
    }
  }
  return { batchItemFailures: failures };
}
HANDLER
