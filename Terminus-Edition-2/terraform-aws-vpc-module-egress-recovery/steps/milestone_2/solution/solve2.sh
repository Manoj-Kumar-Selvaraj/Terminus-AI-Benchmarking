#!/usr/bin/env bash
set -Eeuo pipefail
python3 - <<'PY'
from pathlib import Path


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old in text:
        return text.replace(old, new, 1)
    if new in text or (label == "nat selection" and 'fmt.Sprint(n["az"]) == az' in text):
        return text
    raise SystemExit(label + " anchor missing")


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
s = replace_once(s, old_nat, new_nat, "nat selection")
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
needle = '''	for _, t := range []string{"public", "app", "data"} {
		if !tiers[t] {
			errs = append(errs, "missing "+t+" tier")
		}
	}
	if len(errs) > 0 {'''
insert = '''	for _, t := range []string{"public", "app", "data"} {
		if !tiers[t] {
			errs = append(errs, "missing "+t+" tier")
		}
	}
	for _, ep := range sliceOfMaps(c["gateway_endpoints"]) {
		svc := fmt.Sprint(ep["service"])
		if svc != "s3" && svc != "dynamodb" {
			errs = append(errs, "unsupported gateway endpoint service: "+svc)
		}
	}
	if len(errs) > 0 {'''
if "unsupported gateway endpoint service" not in s:
    s = replace_once(s, needle, insert, "validate_config")
s = replace_once(
    s,
    '''	for _, rt := range rts {
		eligible = append(eligible, fmt.Sprint(rt["id"]))
	}''',
    '''	for _, rt := range rts {
		if fmt.Sprint(rt["tier"]) == "app" {
			eligible = append(eligible, fmt.Sprint(rt["id"]))
		}
	}''',
    "endpoint attachment",
)
p.write_text(s)
PY
/usr/local/go/bin/gofmt -w /app/infra/modules/vpc/module.go
/usr/local/go/bin/go build -o /app/bin/vpcsim /app/cmd/vpcsim
