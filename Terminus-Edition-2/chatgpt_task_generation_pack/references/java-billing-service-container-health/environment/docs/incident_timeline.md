# Incident timeline

04:11 UTC: billing-service pods reported ready=0 while the Java process remained running.

04:18 UTC: after a datasource hotfix, readiness recovered but soak traffic began returning
503 responses with `pool exhausted` in application logs.

04:27 UTC: memory limits were tightened during cost review. Pods began exiting with
OOMKilled even though the JVM heap looked modest on paper.

04:36 UTC: a schema migration release lengthened startup. The platform restarted pods
during migration and the rollout never stabilized.
