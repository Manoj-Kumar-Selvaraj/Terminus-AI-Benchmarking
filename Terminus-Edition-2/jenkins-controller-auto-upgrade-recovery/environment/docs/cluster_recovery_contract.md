# Cluster recovery contract

Full recovery must reconcile controller ownership, agents, the work queue, and production start.

## Controller election

Elect the controller from `cluster/topology.json`. Eligible pods must satisfy all of these conditions:

- The pod is active.
- The pod mounts the Jenkins home.
- The pod has read/write access.
- The pod does not have `recovery_eligible: false`.

Select the eligible pod with the highest numeric `recovery_priority`. A missing priority ranks below any explicit priority. Ties break by ascending pod name.

`plan --json` must expose the selected pod as top-level string `elected_controller`. If no eligible controller exists, fail before cumulative mutation with stderr containing `no eligible controller`.

## Controller fencing and service routing

Keep exactly the elected controller active and read/write. Fence other home-mounting controllers from write access without deleting their pods.

Preserve observers, pod metadata, topology metadata, and the ReadWriteOnce claim. Route service traffic to the elected controller.

## Agent recovery

Resolve `required_agent_java` from `config/version_contract.json`. Upgrade only online agents whose runtime is incompatible with `required_agent_java`.

Leave compatible agents, offline agents, and all agent metadata unchanged.

## Queue recovery

Deduplicate `jenkins_home/queue.json` by ID. Keep the complete first record in first-seen order and preserve unknown fields.

## Cluster commit and start

The `after_cluster_commit_response_lost` fault point exits non-zero after durable cluster and queue commits. Resuming with the same owner must not create a duplicate `cluster_committed` event.

After all durable phases complete, invoke the simulator `start` command through the simulator path defined in `simulator_contract.md`. Do not write simulator outputs directly.

Successful full recovery must record exactly one `cluster_committed` before `operation_completed`, reach `READY` diagnostics status, and remain idempotent on replay.