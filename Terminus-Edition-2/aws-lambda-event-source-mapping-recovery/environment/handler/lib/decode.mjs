import { MessageFailure } from "./errors.mjs";

export function decodeBody(record) {
  const body = record?.body ?? "";
  try {
    if (typeof body === "string") return JSON.parse(body);
    if (typeof body === "object" && body !== null) return body;
  } catch {
    throw new MessageFailure("MALFORMED_JSON");
  }
  throw new MessageFailure("MALFORMED_JSON");
}
