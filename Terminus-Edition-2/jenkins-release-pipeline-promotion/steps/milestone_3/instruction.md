# Milestone 3 — Gate promotion on the built artifact, not branch tip

The pipeline now runs clean integration axes, but the quality gate evaluates the branch tip rather than the artifact being promoted. Use `/app/evidence/quality_gate_miss.log`. Promotion must depend on scan status for the built artifact digest and must keep the legacy manifest schema.
