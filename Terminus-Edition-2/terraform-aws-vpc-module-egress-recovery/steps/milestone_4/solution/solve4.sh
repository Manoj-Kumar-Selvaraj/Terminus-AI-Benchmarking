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
if '"net"' not in s:
    s = s.replace(
        'import (\n\t"fmt"\n\t"sort"\n\t"strings"\n)',
        'import (\n\t"fmt"\n\t"net"\n\t"sort"\n\t"strings"\n)',
        1,
    )
needle = '''	for _, t := range []string{"public", "app", "data"} {
		if !tiers[t] {
			errs = append(errs, "missing "+t+" tier")
		}
	}
	if len(errs) > 0 {'''
insert_m2 = '''	for _, t := range []string{"public", "app", "data"} {
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
    s = replace_once(s, needle, insert_m2, "m2 validate")
needle = '''	for _, ep := range sliceOfMaps(c["gateway_endpoints"]) {
		svc := fmt.Sprint(ep["service"])
		if svc != "s3" && svc != "dynamodb" {
			errs = append(errs, "unsupported gateway endpoint service: "+svc)
		}
	}
	if len(errs) > 0 {'''
insert_m3 = '''	for _, ep := range sliceOfMaps(c["gateway_endpoints"]) {
		svc := fmt.Sprint(ep["service"])
		if svc != "s3" && svc != "dynamodb" {
			errs = append(errs, "unsupported gateway endpoint service: "+svc)
		}
	}
	if _, vpcNet, err := net.ParseCIDR(fmt.Sprint(c["vpc_cidr"])); err != nil {
		errs = append(errs, "invalid cidr configuration: "+err.Error())
	} else {
		seen := []struct {
			name string
			net  *net.IPNet
		}{}
		for _, subnet := range sliceOfMaps(c["subnets"]) {
			_, sn, err := net.ParseCIDR(fmt.Sprint(subnet["cidr"]))
			if err != nil {
				errs = append(errs, "invalid cidr configuration: "+err.Error())
				continue
			}
			if !cidrSubnetOf(sn, vpcNet) {
				errs = append(errs, "subnet "+fmt.Sprint(subnet["name"])+" outside vpc_cidr")
			}
			for _, prev := range seen {
				if cidrOverlaps(sn, prev.net) {
					errs = append(errs, "subnet "+fmt.Sprint(subnet["name"])+" overlaps "+prev.name)
				}
			}
			seen = append(seen, struct {
				name string
				net  *net.IPNet
			}{fmt.Sprint(subnet["name"]), sn})
		}
	}
	if len(errs) > 0 {'''
if "outside vpc_cidr" not in s:
    s = replace_once(s, needle, insert_m3, "m3 validate")
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
old_prior = '''	if priorState != nil {
		actions = append(actions, map[string]interface{}{
			"action":   "replace",
			"resource": "aws_route_table.private",
			"reason":   "legacy index drift",
		})
	} else {'''
new_prior = '''	if priorState != nil {
		if vpc, ok := priorState["vpc"].(map[string]interface{}); ok {
			if fmt.Sprint(vpc["cidr"]) == fmt.Sprint(vpcObj["cidr"]) {
				// unchanged imported VPC CIDR: no destructive replacements
			}
		}
	} else {'''
s = replace_once(s, old_prior, new_prior, "prior_state")
flow_needle = "\toutputs := map[string]interface{}{"
flow_block = '''	flowLog := map[string]interface{}{
		"id":            id("fl", env, "vpc"),
		"traffic_type":  "ALL",
		"destination":   mapString(c, "flow_log", "destination"),
		"iam_policy": map[string]interface{}{
			"Action": []string{
				"logs:CreateLogStream",
				"logs:PutLogEvents",
				"logs:DescribeLogGroups",
			},
			"Resource": mapString(c, "flow_log", "log_group_arn"),
		},
		"log_format": "${version} ${account-id} ${interface-id} ${srcaddr} ${dstaddr} ${action}",
		"subnet_ids": sortedAllSubnetIDs(subs),
	}
	cidrs := stringSlice(mapMap(c, "resolver"), "allowed_cidrs")
	var ingress []map[string]interface{}
	for _, proto := range []string{"tcp", "udp"} {
		ingress = append(ingress, map[string]interface{}{
			"protocol":    proto,
			"from_port":   53,
			"to_port":     53,
			"cidr_blocks": append([]string(nil), cidrs...),
		})
	}
	resolverSG := map[string]interface{}{
		"id": id("sg", env, "resolver-inbound"),
		"ingress": ingress,
		"egress": []map[string]interface{}{
			{
				"protocol":    "-1",
				"from_port":   0,
				"to_port":     0,
				"cidr_blocks": []string{fmt.Sprint(c["vpc_cidr"])},
			},
		},
	}
	outputs := map[string]interface{}{'''
if '"traffic_type":  "ALL"' not in s and flow_needle in s:
    s = s.replace(flow_needle, flow_block, 1)
    s = s.replace('"flow_log":                  nil,', '"flow_log":                  flowLog,')
    s = s.replace('"resolver_security_group":   nil,', '"resolver_security_group":   resolverSG,')
helpers = '''

func mapString(c map[string]interface{}, section, key string) string {
	if sec, ok := c[section].(map[string]interface{}); ok {
		return fmt.Sprint(sec[key])
	}
	return ""
}

func mapMap(c map[string]interface{}, section string) map[string]interface{} {
	if sec, ok := c[section].(map[string]interface{}); ok {
		return sec
	}
	return map[string]interface{}{}
}

func stringSlice(m map[string]interface{}, key string) []string {
	raw, _ := m[key].([]interface{})
	out := make([]string, 0, len(raw))
	for _, item := range raw {
		out = append(out, fmt.Sprint(item))
	}
	return out
}

func sortedAllSubnetIDs(subs []map[string]interface{}) []string {
	ids := make([]string, 0, len(subs))
	for _, s := range subs {
		ids = append(ids, fmt.Sprint(s["id"]))
	}
	sort.Strings(ids)
	return ids
}

func cidrSubnetOf(child, parent *net.IPNet) bool {
	if child == nil || parent == nil {
		return false
	}
	cp := parent.Mask
	pp := parent.IP
	if len(child.Mask) == len(cp) {
		for i := range cp {
			if child.Mask[i] < cp[i] {
				return false
			}
		}
	}
	for i := range child.IP {
		if child.IP[i]&cp[i] != pp[i]&cp[i] {
			return false
		}
	}
	return true
}

func cidrOverlaps(a, b *net.IPNet) bool {
	if a == nil || b == nil {
		return false
	}
	onesA, _ := a.Mask.Size()
	onesB, _ := b.Mask.Size()
	if onesA < onesB {
		return a.Contains(b.IP)
	}
	return b.Contains(a.IP)
}
'''
if "func cidrSubnetOf" not in s:
    s += helpers
p.write_text(s)
PY
/usr/local/go/bin/gofmt -w /app/infra/modules/vpc/module.go
/usr/local/go/bin/go build -o /app/bin/vpcsim /app/cmd/vpcsim
