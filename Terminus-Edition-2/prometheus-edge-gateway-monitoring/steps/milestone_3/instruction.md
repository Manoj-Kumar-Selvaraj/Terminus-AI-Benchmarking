# Milestone 3: Make rate windows restart and reset safe

You are on call for `prometheus-edge-gateway-monitoring`. The production system is represented by an offline simulator under `/app/tools/edge_metrics.py`. Evidence is under `/app/docs`, and the working state/output directories are `/app/state` and `/app/out`.

Repair the real simulator workflow so this milestone's symptom is resolved without breaking previous milestones. Preserve the documented CLI flags, state files, manifest/control schemas, environment names, and output JSON keys. Do not replace the tool with a fixture-specific script, do not edit tests, and do not delete persisted operator evidence unless the runbook explicitly says it is transient.

Expected outcome: the simulator should handle this milestone's incident behavior deterministically, fail closed on malformed or unsafe inputs, and leave auditable state in the documented output paths.
