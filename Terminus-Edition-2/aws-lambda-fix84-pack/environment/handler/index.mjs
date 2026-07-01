import { processBatch } from "./lib/batch.mjs";

export async function handler(event) {
  return processBatch(event?.Records || []);
}
