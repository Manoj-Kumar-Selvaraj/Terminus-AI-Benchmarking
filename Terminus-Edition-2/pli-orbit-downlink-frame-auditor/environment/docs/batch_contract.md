# Batch Contract

The operator command is `/app/scripts/run_batch.sh`. The task may be repaired by changing the PL/I-style control decks under `/app/src/` and the local batch harness under `/app/scripts/`, but the public command path, input files, state files, and output schemas must remain compatible.

The harness is offline-only. It must not require a real PL/I compiler, network access, external services, or live telemetry systems.
