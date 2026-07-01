import { writeFileSync } from "node:fs";
import { handler } from "./index.mjs";

const chunks = [];
for await (const chunk of process.stdin) {
  chunks.push(chunk);
}

const event = JSON.parse(Buffer.concat(chunks).toString("utf8"));
const result = await handler(event);

const capturePath = process.env.POST_HANDLER_RECORDS_PATH;
if (capturePath) {
  writeFileSync(capturePath, `${JSON.stringify(event.Records ?? [], null, 2)}\n`);
}

process.stdout.write(JSON.stringify(result));
