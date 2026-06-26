#!/usr/bin/env bash
set -Eeuo pipefail
APP_DIR="${APP_DIR:-/app}"
python3 - <<'PY'
from pathlib import Path

p = Path("/app/infra/modules/vpc/module.go")
s = p.read_text()
old_nat = '''func natGateway(c map[string]interface{}, az string) string {
	nats, _ := c["nat_gateways"].([]interface{})
	if len(nats) == 0 {
		return ""
	}
	if n, ok := nats[0].(map[string]interface{}); ok {
		return fmt.Sprint(n["id"])
	}
	return ""
}'''
new_nat = '''func natGateway(c map[string]interface{}, az string) string {
	nats, _ := c["nat_gateways"].([]interface{})
	for _, raw := range nats {
		n, ok := raw.(map[string]interface{})
		if !ok {
			continue
		}
		if fmt.Sprint(n["az"]) == az {
			return fmt.Sprint(n["id"])
		}
	}
	return ""
}'''
if old_nat in s:
    s = s.replace(old_nat, new_nat, 1)
elif "fmt.Sprint(n[\"az\"]) == az" in s:
    pass
else:
    raise SystemExit("nat selection anchor missing")
data_block = ''' else if tier == "data" {
			if nat := natGateway(c, az); nat != "" {
				routes = append(routes, map[string]interface{}{
					"destination": "0.0.0.0/0",
					"target":      nat,
				})
			}
		}'''
if data_block in s:
    s = s.replace(data_block, "", 1)
p.write_text(s)
PY
/usr/local/go/bin/gofmt -w /app/infra/modules/vpc/module.go
/usr/local/go/bin/go build -o /app/bin/vpcsim /app/cmd/vpcsim
