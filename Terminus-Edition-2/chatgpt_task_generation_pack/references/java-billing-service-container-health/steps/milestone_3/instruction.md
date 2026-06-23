Platform cost review lowered the billing pod memory limit to 256Mi and pods began exiting with OOMKilled despite modest JVM settings on paper. Review `/app/evidence/kube_events.txt`, `/app/docs/container_runtime_contract.md`, and `/app/config/jvm.options`. Keep the service stable under the published container memory limit.

Preserve milestone 1 readiness and milestone 2 pool cleanup. The verifier inspects JVM startup options for container-aware heap sizing that fits the 256Mi limit.
