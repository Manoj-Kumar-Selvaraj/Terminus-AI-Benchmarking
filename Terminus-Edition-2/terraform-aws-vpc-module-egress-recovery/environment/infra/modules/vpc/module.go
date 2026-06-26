package vpc

import (
	"fmt"
	"sort"
	"strings"
)

type ModuleError struct {
	Msg string
}

func (e *ModuleError) Error() string { return e.Msg }

func id(prefix string, parts ...interface{}) string {
	encoded := make([]string, len(parts))
	for i, p := range parts {
		s := fmt.Sprint(p)
		s = strings.ReplaceAll(s, "/", "_")
		s = strings.ReplaceAll(s, ".", "_")
		encoded[i] = s
	}
	return prefix + "-" + strings.Join(encoded, "-")
}

func azSuffix(az string) string { return az[len(az)-1:] }

func natGateway(c map[string]interface{}, az string) string {
	nats, _ := c["nat_gateways"].([]interface{})
	if len(nats) == 0 {
		return ""
	}
	if n, ok := nats[0].(map[string]interface{}); ok {
		return fmt.Sprint(n["id"])
	}
	return ""
}

func ValidateConfig(c map[string]interface{}) error {
	var errs []string
	if fmt.Sprint(c["environment"]) == "" {
		errs = append(errs, "environment is required")
	}
	azs, _ := c["availability_zones"].([]interface{})
	if len(azs) < 2 {
		errs = append(errs, "at least two azs required")
	}
	tiers := map[string]bool{}
	for _, raw := range sliceOfMaps(c["subnets"]) {
		tiers[fmt.Sprint(raw["tier"])] = true
	}
	for _, t := range []string{"public", "app", "data"} {
		if !tiers[t] {
			errs = append(errs, "missing "+t+" tier")
		}
	}
	if len(errs) > 0 {
		return &ModuleError{Msg: strings.Join(errs, "; ")}
	}
	return nil
}

func Render(c map[string]interface{}, priorState map[string]interface{}) (map[string]interface{}, error) {
	if err := ValidateConfig(c); err != nil {
		return nil, err
	}
	env := fmt.Sprint(c["environment"])
	vpcObj := map[string]interface{}{
		"id":   id("vpc", env),
		"cidr": c["vpc_cidr"],
		"tags": map[string]interface{}{
			"Environment": env,
			"ManagedBy":   "terraform-aws-vpc-module",
		},
	}
	var subs []map[string]interface{}
	var rts []map[string]interface{}
	for _, s := range sliceOfMaps(c["subnets"]) {
		tier := fmt.Sprint(s["tier"])
		az := fmt.Sprint(s["az"])
		rt := id("rtb", env, tier, azSuffix(az))
		sid := id("subnet", env, tier, azSuffix(az))
		subs = append(subs, map[string]interface{}{
			"id":             sid,
			"name":           s["name"],
			"tier":           tier,
			"az":             az,
			"cidr":           s["cidr"],
			"route_table_id": rt,
			"address":        fmt.Sprintf(`module.vpc.aws_subnet.%s["%s"]`, tier, az),
			"tags": map[string]interface{}{
				"Name":             s["name"],
				"Tier":             tier,
				"AvailabilityZone": az,
				"Environment":      env,
			},
		})
		routes := []map[string]interface{}{}
		if tier == "public" {
			igw := c["internet_gateway_id"]
			if igw == nil {
				igw = "igw"
			}
			routes = append(routes, map[string]interface{}{
				"destination": "0.0.0.0/0",
				"target":      igw,
			})
		} else if tier == "app" {
			if nat := natGateway(c, az); nat != "" {
				routes = append(routes, map[string]interface{}{
					"destination": "0.0.0.0/0",
					"target":      nat,
				})
			}
		} else if tier == "data" {
			if nat := natGateway(c, az); nat != "" {
				routes = append(routes, map[string]interface{}{
					"destination": "0.0.0.0/0",
					"target":      nat,
				})
			}
		}
		rts = append(rts, map[string]interface{}{
			"id":     rt,
			"tier":   tier,
			"az":     az,
			"routes": routes,
			"tags": map[string]interface{}{
				"Tier":             tier,
				"AvailabilityZone": az,
				"ManagedBy":        "terraform-aws-vpc-module",
			},
		})
	}
	eligible := make([]string, 0, len(rts))
	for _, rt := range rts {
		eligible = append(eligible, fmt.Sprint(rt["id"]))
	}
	sort.Strings(eligible)
	accountID := c["account_id"]
	if accountID == nil {
		accountID = "000000000000"
	}
	var endpoints []map[string]interface{}
	for _, ep := range sliceOfMaps(c["gateway_endpoints"]) {
		svc := fmt.Sprint(ep["service"])
		endpoints = append(endpoints, map[string]interface{}{
			"id":              id("vpce", env, svc),
			"service":         svc,
			"route_table_ids": append([]string(nil), eligible...),
			"policy": map[string]interface{}{
				"Statement": []map[string]interface{}{
					{
						"Action":   []string{svc + ":*"},
						"Resource": "*",
						"Condition": map[string]interface{}{
							"StringEquals": map[string]interface{}{
								"aws:PrincipalAccount": accountID,
							},
						},
					},
				},
			},
			"tags": map[string]interface{}{
				"ManagedBy":   "terraform-aws-vpc-module",
				"Environment": env,
			},
		})
	}
	outputs := map[string]interface{}{
		"vpc_id":                        vpcObj["id"],
		"public_subnet_ids":             sortedIDs(subs, "public"),
		"private_app_subnet_ids":        sortedIDs(subs, "app"),
		"isolated_data_subnet_ids":      sortedIDs(subs, "data"),
		"private_app_route_table_ids":   sortedRTIDs(rts, "app"),
		"isolated_data_route_table_ids": sortedRTIDs(rts, "data"),
	}
	state := map[string]interface{}{
		"schema_version":            "vpcsim.aws.1",
		"environment":               env,
		"vpc":                       vpcObj,
		"subnets":                   subs,
		"route_tables":              rts,
		"gateway_endpoints":         endpoints,
		"flow_log":                  nil,
		"resolver_security_group":   nil,
		"outputs":                   outputs,
		"moved":                     []interface{}{},
	}
	actions := []map[string]interface{}{}
	if priorState != nil {
		actions = append(actions, map[string]interface{}{
			"action":   "replace",
			"resource": "aws_route_table.private",
			"reason":   "legacy index drift",
		})
	} else {
		actions = append(actions, map[string]interface{}{
			"action": "create",
			"resource": "vpc",
			"id":     vpcObj["id"],
		})
	}
	state["plan_actions"] = actions
	return state, nil
}

func sliceOfMaps(v interface{}) []map[string]interface{} {
	raw, _ := v.([]interface{})
	out := make([]map[string]interface{}, 0, len(raw))
	for _, item := range raw {
		if m, ok := item.(map[string]interface{}); ok {
			out = append(out, m)
		}
	}
	return out
}

func sortedIDs(subs []map[string]interface{}, tier string) []string {
	var ids []string
	for _, s := range subs {
		if fmt.Sprint(s["tier"]) == tier {
			ids = append(ids, fmt.Sprint(s["id"]))
		}
	}
	sort.Strings(ids)
	return ids
}

func sortedRTIDs(rts []map[string]interface{}, tier string) []string {
	var ids []string
	for _, rt := range rts {
		if fmt.Sprint(rt["tier"]) == tier {
			ids = append(ids, fmt.Sprint(rt["id"]))
		}
	}
	sort.Strings(ids)
	return ids
}
