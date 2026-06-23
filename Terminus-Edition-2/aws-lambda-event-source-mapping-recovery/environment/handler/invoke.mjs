import { handler } from "./index.mjs";

const chunks = [];
for await (const chunk of process.stdin) {
  chunks.push(chunk);
}

const event = JSON.parse(Buffer.concat(chunks).toString("utf8"));
const result = await handler(event);
process.stdout.write(JSON.stringify(result));
