# Quality gate contract

The quality gate report uses status `pass` or `fail` and carries both `commit_sha` and `artifact_hash`. Promotion must fail closed when the gate is missing, failed, malformed, or does not belong to the exact artifact being promoted. A submitted gate with status `pass` but an empty `commit_sha` or empty `artifact_hash` is a provenance mismatch. The simulator must not borrow missing gate provenance from the generated artifact manifest.

Blocked runs write `release/blocked_promotion.json` using schema `blocked-promotion/v1`. It contains `status: "blocked"`, a diagnostic `reason`, the submitted `quality_gate` object exactly as materialized from the input gate without provenance autofill, and the generated `artifact_manifest` object. Commit mismatch reasons identify a match or provenance failure; artifact-hash mismatch reasons identify the artifact failure.
