# Local runbook

Build with `/usr/local/go/bin/go build ./...` and run `/app/scripts/run_service.sh`. The gateway listens on port 8080 and reads `/app/config/limits.json` unless `TRAFFIC_POLICY_PATH` is set. Review incident evidence before changing the limiter or middleware contracts.
