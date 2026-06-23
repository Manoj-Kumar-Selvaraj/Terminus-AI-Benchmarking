After the replacement issuer was trusted, calls to the same ledger route still failed because service discovery connected to an IP address while the certificate represented the routed service identity. Review `/app/evidence/hostname_failure.log`, `/app/docs/hostname_contract.md`, the existing gateway configuration flow, and `/app/internal/tlsmaterial/manager.go`. Restore successful verified handshakes for the configured route identity.

Keep milestone 1 behavior intact. The gateway must continue using the configured private trust material, and verification may not be disabled or replaced with acceptance of arbitrary names.

Success is verified by the milestone Go tests under `/app/internal/tlsmaterial` passing with `go test -race`.
