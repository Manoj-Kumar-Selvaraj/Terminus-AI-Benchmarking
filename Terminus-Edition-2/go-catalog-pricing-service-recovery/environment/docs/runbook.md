# Local runbook

Build all packages:

```bash
/usr/local/go/bin/go test ./...
/usr/local/go/bin/go build -o /app/build/pricingd ./cmd/pricingd
```

Run the service:

```bash
/app/scripts/run_service.sh
```

Useful incident material is under `/app/evidence`; behavioral contracts are under `/app/docs`.
