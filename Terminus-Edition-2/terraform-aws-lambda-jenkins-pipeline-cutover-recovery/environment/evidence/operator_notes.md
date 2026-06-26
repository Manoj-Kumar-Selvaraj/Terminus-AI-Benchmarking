# Operator Notes

The Jenkins job must remain available as a read-only comparison path during rollout. It cannot be used as a permanent fallback writer after Lambda becomes primary.

Do not solve the incident by increasing all Lambda timeouts to 900 seconds, setting unreserved concurrency, granting `*`, disabling retries, deleting state, or routing every stage through one shared function identity.

The trusted runtime is `/opt/task-tools/lambda-pipeline-runtime`. Its state and binary are protected. Use its public commands and inspect output rather than editing `/var/lib/lambda-pipeline-runtime`.
