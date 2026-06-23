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
import { writeFileSync } from "node:fs";
import { appendLedgerEntry, loadLedger, ledgerPath } from "./lib/ledger.mjs";

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

function recordDuplicateEvidence(eventId, messageId) {
  const entries = loadLedger();
  let changed = false;
  for (const entry of entries) {
    if (entry.business_event_id !== eventId) {
      continue;
    }
    const seen = new Set(entry.duplicate_message_ids || []);
    if (messageId !== entry.message_id) {
      seen.add(messageId);
    }
    entry.duplicate_message_ids = [...seen];
    changed = true;
    break;
  }
  if (changed) {
    writeFileSync(ledgerPath(), `${JSON.stringify(entries, null, 2)}\n`);
  }
}

function alreadyCommitted(eventId, messageId) {
  for (const entry of loadLedger()) {
    if (entry.business_event_id === eventId) {
      return true;
    }
    if (messageId && entry.message_id === messageId) {
      return true;
    }
  }
  return false;
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
  const messageId = record.messageId;
  const eventId = body.business_event_id;
  if (alreadyCommitted(eventId, messageId)) {
    recordDuplicateEvidence(eventId, messageId);
    return;
  }
  appendLedgerEntry({
    message_id: messageId,
    business_event_id: eventId,
    account_id: body.account_id,
    amount_cents: body.amount_cents,
    currency: body.currency,
    operation: body.operation,
    status: "COMMITTED",
    duplicate_message_ids: [],
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
