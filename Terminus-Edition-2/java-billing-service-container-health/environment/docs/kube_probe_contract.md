# Kubernetes probe contract

The billing deployment manifest is `/app/deploy/kube/billing-deployment.yaml`.

Probe requirements:

- `readinessProbe` must call `/health/ready` on port 8080.
- `livenessProbe` must call `/health/live` only. The liveness probe section must not
  reference `/health/ready`.
- Startup safety requires either a `startupProbe` section or
  `livenessProbe.initialDelaySeconds` of at least 12 so migrations can finish before
  the kubelet restarts the pod.

`/health/live` must return HTTP 200 during migrations. `/health/ready` may return
HTTP 503 until migration and datasource checks succeed.
