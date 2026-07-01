import { decodeBody } from "./decode.mjs";
import { validateRecord } from "./validate.mjs";
import { commitRecord } from "./ledger.mjs";

export async function processRecord(record) {
  const body = decodeBody(record);
  await validateRecord(body);
  await commitRecord({
    message_id: record.messageId,
    business_event_id: body.business_event_id,
    account_id: body.account_id,
    amount_cents: body.amount_cents,
    currency: body.currency,
    operation: body.operation,
    status: "COMMITTED",
  });
}
