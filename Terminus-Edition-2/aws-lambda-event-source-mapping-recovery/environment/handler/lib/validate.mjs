import { setTimeout as sleep } from "node:timers/promises";
import { MessageFailure } from "./errors.mjs";

const REQUIRED = [
  "business_event_id",
  "account_id",
  "amount_cents",
  "currency",
  "operation",
];

export async function validateRecord(body) {
  const delay = Number(body.fixture_delay_ms || 0);
  if (Number.isFinite(delay) && delay > 0) await sleep(Math.min(delay, 250));
  if (body.fixture_infrastructure_failure === true) {
    throw new Error("simulated persistence dependency failure");
  }
  if (body.poison === true) {
    throw new MessageFailure(body.failure_reason || "POISON_MESSAGE");
  }
  if (REQUIRED.some((key) => !(key in body))) {
    throw new MessageFailure("SCHEMA_INVALID");
  }
}
