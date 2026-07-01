import { readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";

function root() {
  return process.env.APP_ROOT || "/app";
}
function readJSON(path) {
  return JSON.parse(readFileSync(path, "utf8"));
}
function stableWrite(path, value) {
  writeFileSync(path, `${JSON.stringify(value, null, 2)}\n`);
}

export function renderPolicy() {
  const app = root();
  const base = readJSON(join(app, "control_plane", "policy_base.json"));
  const grantSet = readJSON(join(app, "control_plane", "queue_grants.json"));
  const queues = readJSON(join(app, "config", "queues.json"));

  const queueStatements = grantSet.grants
    .filter((grant) => grant.status !== "disabled")
    .map((grant) => ({
      Sid: grant.sid,
      Effect: "Allow",
      Action: grant.actions.filter((action) => !action.includes("Visibility")),
      Resource: queues[grant.queue_ref],
    }));

  const rendered = {
    Version: base.Version,
    Statement: [...base.Statement, ...queueStatements],
  };
  stableWrite(join(app, "config", "lambda_role_policy.json"), rendered);
  return rendered;
}

if (import.meta.url === `file://${process.argv[1]}`) {
  renderPolicy();
}
