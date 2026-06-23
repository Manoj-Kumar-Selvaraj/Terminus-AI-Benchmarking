# Batch Contract

Keep `/app/scripts/run_batch.sh` as the public entrypoint. Repair `/app/scripts/pli_premium.awk` and the PL-I-style files under `/app/src` as needed, while preserving their existing formats and the output contracts in `/app/docs/operations.md`. Do not replace the batch path with a separate program that the entrypoint does not invoke.
