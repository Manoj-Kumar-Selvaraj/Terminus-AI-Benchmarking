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
import { createHash } from "node:crypto";
import { readFileSync, writeFileSync } from "node:fs";
import { appendLedgerEntry, loadLedger, ledgerPath } from "./lib/ledger.mjs";

const contract = JSON.parse(readFileSync("/app/config/cutover_contract.json", "utf8"));
class MessageFailure extends Error { constructor(reason){ super(reason); this.reason=reason; } }
function decodeBody(record){ try { return typeof record.body === "string" ? JSON.parse(record.body) : record.body; } catch { throw new MessageFailure("MALFORMED_JSON"); } }
function digest(body){ const stable=[body.account_id,body.amount_cents,body.currency,body.operation]; return createHash("sha256").update(JSON.stringify(stable)).digest("hex"); }
function save(entries){ writeFileSync(ledgerPath(), `${JSON.stringify(entries,null,2)}\n`); }
function validateEnvelope(record, body){
  if (record.eventSourceARN !== contract.active_source_queue_arn) throw new MessageFailure("STALE_SOURCE_QUEUE");
  const version = body.event_version ?? 1;
  if (!contract.accepted_event_versions.includes(version)) throw new MessageFailure("UNSUPPORTED_EVENT_VERSION");
  if (version === 2 && body.cutover_epoch !== contract.cutover_epoch) throw new MessageFailure("STALE_CUTOVER_EPOCH");
  if (body.operation !== contract.required_operation) throw new MessageFailure("UNSUPPORTED_OPERATION");
}
function processRecord(record){
  const body=decodeBody(record);
  if (body.poison === true) throw new MessageFailure(body.failure_reason || "POISON_MESSAGE");
  const required=["business_event_id","account_id","amount_cents","currency","operation"];
  if (!body || required.some(k => !(k in body))) throw new MessageFailure("SCHEMA_INVALID");
  validateEnvelope(record,body);
  const entries=loadLedger(); const existing=entries.find(e=>e.business_event_id===body.business_event_id); const d=digest(body);
  if(existing){
    const old=existing.payload_digest || createHash("sha256").update(JSON.stringify([existing.account_id,existing.amount_cents,existing.currency,existing.operation])).digest("hex");
    if(old!==d) throw new MessageFailure("IDEMPOTENCY_CONFLICT");
    const alternates=[...(existing.duplicate_message_ids || [])];
    if(record.messageId!==existing.message_id && !alternates.includes(record.messageId)) alternates.push(record.messageId);
    existing.duplicate_message_ids=alternates; existing.payload_digest=old; save(entries); return;
  }
  appendLedgerEntry({message_id:record.messageId,business_event_id:body.business_event_id,account_id:body.account_id,amount_cents:body.amount_cents,currency:body.currency,operation:body.operation,status:"COMMITTED",payload_digest:d,duplicate_message_ids:[]});
}
export async function handler(event){ const failures=[]; for(const record of event.Records || []){ try{ processRecord(record); } catch(err){ if(err instanceof MessageFailure){ failures.push({itemIdentifier:record.messageId,failureClassification:err.reason}); continue; } throw err; } } return {batchItemFailures:failures}; }
HANDLER
