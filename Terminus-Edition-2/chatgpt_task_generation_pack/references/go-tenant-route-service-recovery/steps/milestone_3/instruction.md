During the next rollout, a request that had already been accepted by the router was dropped as soon as termination started. Review `/app/evidence/shutdown_trace.txt`, `/app/docs/rollout_contract.md`, and the HTTP service lifecycle code. Make termination behavior honor the rollout contract for accepted requests.

Keep the earlier route refresh and upstream resource fixes. The verifier starts a real HTTP server, begins a slow but valid request, triggers service termination, and expects the accepted request to complete inside the provided grace context.
