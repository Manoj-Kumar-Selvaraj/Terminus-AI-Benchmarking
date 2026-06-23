# Artifact manifest schema

`/app/out/.../manifests/artifact_manifest.json` uses `artifact-manifest/v1` with `build_number`, `commit_sha`, `branch`, `artifact_hash`, `artifact_path`, and `created_by`. Downstream stages consume the manifest, not branch state.
