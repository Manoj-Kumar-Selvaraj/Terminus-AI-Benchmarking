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
  const records = event.Records || [];
  try {
    for (const record of records) {
      processRecord(record);
    }
    return { batchItemFailures: [] };
  } catch (err) {
    if (err instanceof MessageFailure) {
      return {
        batchItemFailures: records.map((record) => ({
          itemIdentifier: record.messageId,
        })),
      };
    }
    throw err;
  }
}
