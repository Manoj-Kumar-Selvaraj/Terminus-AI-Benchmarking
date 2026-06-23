# Incident timeline

10:13 Build 4187 created an artifact for a release candidate commit. 10:19 downstream stages reported a different commit. 10:31 parallel package promotion intermittently referenced integration workspace data. 10:44 a failed gate was still promoted. 11:06 rollback rebuilt from branch tip instead of restoring the previously promoted artifact.
