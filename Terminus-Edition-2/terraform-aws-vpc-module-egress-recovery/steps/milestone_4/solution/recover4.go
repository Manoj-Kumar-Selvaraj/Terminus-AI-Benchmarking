package main

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"net"
	"os"
	"path/filepath"
	"sort"
	"strings"
)

const featureLevel = 4

type Recovery struct {
	Root              string
	Config            map[string]any
	ObservedRoutes    map[string]any
	ObservedEndpoints map[string]any
	Imported          map[string]any
	NatHealth         map[string]any
	Audit             map[string]any
}

type JournalRecord struct {
	Event        string `json:"event"`
	Owner        string `json:"owner,omitempty"`
	ConfigDigest string `json:"config_digest,omitempty"`
	Stage        string `json:"stage,omitempty"`
	StateDigest  string `json:"state_digest,omitempty"`
}

func main() {
	if len(os.Args) < 2 {
		die("subcommand required")
	}
	cmd := os.Args[1]
	fs := flag.NewFlagSet(cmd, flag.ExitOnError)
	root := fs.String("root", "/app", "incident root")
	jsonOut := fs.Bool("json", false, "json output")
	owner := fs.String("owner", "", "recovery owner")
	failAfter := fs.String("fail-after", "", "failure injection stage")
	_ = fs.Parse(os.Args[2:])
	r, err := LoadRecovery(*root)
	if err != nil {
		failJSON(*jsonOut, err)
		return
	}
	switch cmd {
	case "inspect":
		state, _ := r.LoadState()
		phase := "ROUTING_DRIFT"
		if state != nil {
			phase = "RECOVERED"
		}
		printJSON(map[string]any{"phase": phase, "feature_level": featureLevel, "evidence_files": []string{"observed_routes.json", "observed_endpoints.json", "imported_tf_state.json", "nat_health.json", "audit_inventory.json"}})
	case "plan":
		st, err := r.BuildState(false)
		if err != nil {
			failJSON(*jsonOut, err)
			return
		}
		st["plan_only"] = true
		printJSON(st)
	case "apply":
		if *owner == "" {
			failJSON(*jsonOut, errors.New("owner is required"))
			return
		}
		if err := r.Apply(*owner, *failAfter); err != nil {
			failJSON(*jsonOut, err)
			return
		}
		printJSON(map[string]any{"applied": true, "owner": *owner})
	case "resume":
		if *owner == "" {
			failJSON(*jsonOut, errors.New("owner is required"))
			return
		}
		if err := r.Resume(*owner); err != nil {
			failJSON(*jsonOut, err)
			return
		}
		printJSON(map[string]any{"resumed": true, "owner": *owner})
	case "verify":
		st, err := r.LoadState()
		if err != nil {
			failJSON(*jsonOut, err)
			return
		}
		ok := st != nil && st["schema_version"] == "vpc-recovery.aws.1"
		printJSON(map[string]any{"valid": ok, "phase": map[bool]string{true: "READY", false: "INCOMPLETE"}[ok]})
	default:
		die("unknown subcommand: " + cmd)
	}
}

func LoadRecovery(root string) (*Recovery, error) {
	r := &Recovery{Root: root}
	var err error
	if r.Config, err = readMap(filepath.Join(root, "infra/envs/prod/vpc_config.json")); err != nil {
		return nil, err
	}
	r.ObservedRoutes, _ = readMap(filepath.Join(root, "evidence/observed_routes.json"))
	r.ObservedEndpoints, _ = readMap(filepath.Join(root, "evidence/observed_endpoints.json"))
	r.Imported, _ = readMap(filepath.Join(root, "evidence/imported_tf_state.json"))
	r.NatHealth, _ = readMap(filepath.Join(root, "evidence/nat_health.json"))
	r.Audit, _ = readMap(filepath.Join(root, "evidence/audit_inventory.json"))
	return r, nil
}

func (r *Recovery) BuildState(final bool) (map[string]any, error) {
	if err := r.ValidateCIDRs(); err != nil {
		return nil, err
	}
	if featureLevel >= 1 {
		if err := r.ValidateNATs(); err != nil {
			return nil, err
		}
	}
	if featureLevel >= 2 {
		if err := r.ValidateEndpoints(); err != nil {
			return nil, err
		}
	}
	if featureLevel >= 4 {
		if err := r.ValidateAudit(); err != nil {
			return nil, err
		}
	}
	env := str(r.Config["environment"])
	if env == "" {
		env = "prod"
	}
	imported := r.ImportByCIDR()
	subs := []map[string]any{}
	rts := []map[string]any{}
	for _, s := range maps(r.Config["subnets"]) {
		tier, az, cidr := str(s["tier"]), str(s["az"]), str(s["cidr"])
		sid := id("subnet", env, tier, azSuffix(az))
		rtid := id("rtb", env, tier, azSuffix(az))
		if featureLevel >= 3 {
			if im, ok := imported[cidr]; ok {
				if str(im["id"]) != "" {
					sid = str(im["id"])
				}
				if str(im["route_table_id"]) != "" {
					rtid = str(im["route_table_id"])
				}
			}
		}
		meta := map[string]any{"source": "desired"}
		obsRT := r.ObservedRoute(tier, az)
		if obsRT != nil {
			if m, ok := obsRT["metadata"].(map[string]any); ok {
				meta = m
			}
		}
		subnet := map[string]any{"id": sid, "name": s["name"], "tier": tier, "az": az, "cidr": cidr, "route_table_id": rtid, "address": fmt.Sprintf("module.vpc.aws_subnet.%s[\"%s\"]", tier, az), "tags": map[string]any{"Name": s["name"], "Tier": tier, "AvailabilityZone": az, "Environment": env}}
		subs = append(subs, subnet)
		routes := []map[string]any{}
		if tier == "public" {
			routes = append(routes, map[string]any{"destination": "0.0.0.0/0", "target": str(r.Config["internet_gateway_id"]), "owner": "terraform-aws-vpc-module"})
		}
		if tier == "app" {
			routes = append(routes, map[string]any{"destination": "0.0.0.0/0", "target": r.NATForAZ(az), "owner": "terraform-aws-vpc-module"})
		}
		if obsRT != nil {
			for _, or := range maps(obsRT["routes"]) {
				if str(or["owner"]) == "manual" {
					routes = append(routes, or)
				}
			}
		}
		rts = append(rts, map[string]any{"id": rtid, "tier": tier, "az": az, "routes": routes, "metadata": meta, "tags": map[string]any{"Tier": tier, "AvailabilityZone": az, "ManagedBy": "terraform-aws-vpc-module"}})
	}
	outputs := map[string]any{"vpc_id": id("vpc", env), "public_subnet_ids": ids(subs, "public"), "private_app_subnet_ids": ids(subs, "app"), "isolated_data_subnet_ids": ids(subs, "data"), "private_app_route_table_ids": rtids(rts, "app"), "isolated_data_route_table_ids": rtids(rts, "data")}
	actions := []map[string]any{}
	actions = append(actions, r.RouteActions(rts)...)
	endpoints := []map[string]any{}
	if featureLevel >= 2 {
		e, ea := r.RenderEndpoints(outputs)
		endpoints = e
		actions = append(actions, ea...)
	}
	moved := []map[string]any{}
	if featureLevel >= 3 {
		moved = r.MovedActions(subs)
		actions = append(actions, moved...)
	}
	var flow any
	var resolver any
	drift := []map[string]any{}
	if featureLevel >= 4 {
		flow, resolver, drift = r.RenderAudit(subs, env)
		for _, d := range drift {
			actions = append(actions, d)
		}
	}
	st := map[string]any{"schema_version": "vpc-recovery.aws.1", "environment": env, "config_digest": r.ConfigDigest(), "vpc": map[string]any{"id": id("vpc", env), "cidr": r.Config["vpc_cidr"], "tags": map[string]any{"Environment": env, "ManagedBy": "terraform-aws-vpc-module"}}, "subnets": subs, "route_tables": rts, "gateway_endpoints": endpoints, "flow_log": flow, "resolver_security_group": resolver, "outputs": outputs, "moved": moved, "drift_report": drift, "plan_actions": actions}
	return st, nil
}

func (r *Recovery) Apply(owner, failAfter string) error {
	if err := r.RepairJournal(); err != nil {
		return err
	}
	st, err := r.BuildState(true)
	if err != nil {
		return err
	}
	if err := r.CheckOwner(owner); err != nil {
		return err
	}
	if failAfter == "" && r.AlreadyCommitted(owner, st) {
		return nil
	}
	if err := r.AppendJournal(JournalRecord{Event: "route_plan_written", Owner: owner, ConfigDigest: r.ConfigDigest(), Stage: "route"}); err != nil {
		return err
	}
	if failAfter == "route_commit" {
		_ = r.WriteState(st)
		_ = r.AppendJournal(JournalRecord{Event: "route_commit_lost", Owner: owner, ConfigDigest: r.ConfigDigest(), Stage: "route"})
		return errors.New("injected failure after route_commit")
	}
	if featureLevel >= 2 {
		if err := r.AppendJournal(JournalRecord{Event: "endpoint_plan_written", Owner: owner, ConfigDigest: r.ConfigDigest(), Stage: "endpoint"}); err != nil {
			return err
		}
		if failAfter == "endpoint_commit" {
			_ = r.WriteState(st)
			_ = r.AppendJournal(JournalRecord{Event: "endpoint_commit_lost", Owner: owner, ConfigDigest: r.ConfigDigest(), Stage: "endpoint"})
			return errors.New("injected failure after endpoint_commit")
		}
	}
	if featureLevel >= 4 {
		_ = r.AppendJournal(JournalRecord{Event: "audit_plan_written", Owner: owner, ConfigDigest: r.ConfigDigest(), Stage: "audit"})
	}
	if featureLevel >= 5 {
		_ = r.AppendJournal(JournalRecord{Event: "state_moves_committed", Owner: owner, ConfigDigest: r.ConfigDigest(), Stage: "moved"})
	}
	if err := r.WriteState(st); err != nil {
		return err
	}
	sd := digestMap(st)
	return r.AppendJournal(JournalRecord{Event: "apply_committed", Owner: owner, ConfigDigest: r.ConfigDigest(), StateDigest: sd})
}
func (r *Recovery) Resume(owner string) error {
	if err := r.RepairJournal(); err != nil {
		return err
	}
	return r.Apply(owner, "")
}

func (r *Recovery) ValidateCIDRs() error {
	if featureLevel < 3 {
		return nil
	}
	_, vpc, err := net.ParseCIDR(str(r.Config["vpc_cidr"]))
	if err != nil {
		return fmt.Errorf("invalid vpc_cidr")
	}
	type nm struct {
		name string
		n    *net.IPNet
	}
	seen := []nm{}
	for _, s := range maps(r.Config["subnets"]) {
		_, n, e := net.ParseCIDR(str(s["cidr"]))
		if e != nil {
			return fmt.Errorf("invalid subnet cidr %s", str(s["name"]))
		}
		if !subnetOf(n, vpc) {
			return fmt.Errorf("subnet %s outside vpc_cidr", str(s["name"]))
		}
		for _, p := range seen {
			if overlaps(n, p.n) {
				return fmt.Errorf("subnet %s overlaps %s", str(s["name"]), p.name)
			}
		}
		seen = append(seen, nm{str(s["name"]), n})
	}
	by := map[string]bool{}
	for _, res := range maps(r.Imported["resources"]) {
		cidr := str(res["cidr"])
		if cidr != "" {
			if by[cidr] {
				return fmt.Errorf("ambiguous imported cidr %s", cidr)
			}
			by[cidr] = true
		}
	}
	return nil
}
func (r *Recovery) ValidateNATs() error {
	for _, s := range maps(r.Config["subnets"]) {
		if str(s["tier"]) == "app" {
			az := str(s["az"])
			if r.NATForAZ(az) == "" {
				return fmt.Errorf("missing nat gateway for app az %s", az)
			}
		}
	}
	return nil
}
func (r *Recovery) ValidateEndpoints() error {
	for _, ep := range maps(r.Config["gateway_endpoints"]) {
		svc := str(ep["service"])
		if svc != "s3" && svc != "dynamodb" {
			return fmt.Errorf("unsupported gateway endpoint service %s", svc)
		}
	}
	for _, ep := range maps(r.ObservedEndpoints["endpoints"]) {
		if !r.EndpointAccountOK(ep) {
			return fmt.Errorf("endpoint policy account mismatch for %s", str(ep["service"]))
		}
	}
	return nil
}
func (r *Recovery) ValidateAudit() error {
	flow := mapMap(r.Audit, "flow_log")
	arn := first(str(mapMap(r.Config, "flow_log")["log_group_arn"]), str(flow["log_group_arn"]))
	parts := strings.Split(arn, ":")
	if len(parts) > 4 && parts[4] != "" && parts[4] != str(r.Config["account_id"]) {
		return fmt.Errorf("flow log destination account mismatch")
	}
	return nil
}

func (r *Recovery) NATForAZ(az string) string {
	health := map[string]string{}
	for _, n := range maps(r.NatHealth["nat_gateways"]) {
		if str(n["state"]) == "available" {
			health[str(n["az"])] = str(n["id"])
		}
	}
	if id := health[az]; id != "" {
		return id
	}
	for _, n := range maps(r.Config["nat_gateways"]) {
		if str(n["az"]) == az {
			return str(n["id"])
		}
	}
	return ""
}
func (r *Recovery) ObservedRoute(tier, az string) map[string]any {
	for _, rt := range maps(r.ObservedRoutes["route_tables"]) {
		if str(rt["tier"]) == tier && str(rt["az"]) == az {
			return rt
		}
	}
	return nil
}
func (r *Recovery) ImportByCIDR() map[string]map[string]any {
	out := map[string]map[string]any{}
	for _, res := range maps(r.Imported["resources"]) {
		if str(res["type"]) == "aws_subnet" || str(res["id"]) != "" {
			out[str(res["cidr"])] = res
		}
	}
	return out
}
func (r *Recovery) RouteActions(rts []map[string]any) []map[string]any {
	a := []map[string]any{}
	for _, rt := range rts {
		obs := r.ObservedRoute(str(rt["tier"]), str(rt["az"]))
		if obs == nil {
			continue
		}
		desired := routeTarget(rt, "0.0.0.0/0")
		old := routeTarget(obs, "0.0.0.0/0")
		if desired != old {
			if desired == "" {
				a = append(a, map[string]any{"action": "delete_route", "route_table_id": rt["id"], "destination": "0.0.0.0/0", "reason": "isolated data subnet"})
			} else {
				a = append(a, map[string]any{"action": "update_route", "route_table_id": rt["id"], "destination": "0.0.0.0/0", "target": desired, "previous_target": old})
			}
		}
	}
	return a
}
func (r *Recovery) RenderEndpoints(outputs map[string]any) ([]map[string]any, []map[string]any) {
	app := stringAny(outputs["private_app_route_table_ids"])
	eps := []map[string]any{}
	acts := []map[string]any{}
	for _, want := range maps(r.Config["gateway_endpoints"]) {
		svc := str(want["service"])
		obs := r.Endpoint(svc)
		eid := id("vpce", str(r.Config["environment"]), svc)
		policy := map[string]any{"Statement": []any{map[string]any{"Action": []any{svc + ":*"}, "Resource": "*", "Condition": map[string]any{"StringEquals": map[string]any{"aws:PrincipalAccount": str(r.Config["account_id"])}}}}}
		tags := map[string]any{"ManagedBy": "terraform-aws-vpc-module", "Environment": str(r.Config["environment"])}
		meta := map[string]any{}
		if obs != nil {
			eid = str(obs["id"])
			if obs["policy"] != nil {
				policy = obs["policy"].(map[string]any)
			}
			if obs["tags"] != nil {
				tags = obs["tags"].(map[string]any)
			}
			if obs["metadata"] != nil {
				meta = obs["metadata"].(map[string]any)
			}
		}
		eps = append(eps, map[string]any{"id": eid, "service": svc, "route_table_ids": app, "policy": policy, "tags": tags, "metadata": meta})
		if obs != nil && !sameStrings(app, stringAny(obs["route_table_ids"])) {
			acts = append(acts, map[string]any{"action": "update_endpoint_association", "endpoint_id": eid, "service": svc, "route_table_ids": app})
		}
	}
	return eps, acts
}
func (r *Recovery) Endpoint(svc string) map[string]any {
	for _, ep := range maps(r.ObservedEndpoints["endpoints"]) {
		if str(ep["service"]) == svc {
			return ep
		}
	}
	return nil
}
func (r *Recovery) EndpointAccountOK(ep map[string]any) bool {
	b, _ := json.Marshal(ep["policy"])
	return strings.Contains(string(b), str(r.Config["account_id"]))
}
func (r *Recovery) MovedActions(subs []map[string]any) []map[string]any {
	appByCIDR := map[string]string{}
	for _, s := range subs {
		if str(s["tier"]) == "app" {
			appByCIDR[str(s["cidr"])] = str(s["address"])
		}
	}
	out := []map[string]any{}
	seen := map[string]bool{}
	for _, res := range maps(r.Imported["resources"]) {
		to := appByCIDR[str(res["cidr"])]
		from := str(res["address"])
		if to != "" && from != "" && from != to && !seen[from] {
			out = append(out, map[string]any{"action": "moved", "from": from, "to": to, "id": res["id"]})
			seen[from] = true
		}
	}
	sort.Slice(out, func(i, j int) bool { return str(out[i]["from"]) < str(out[j]["from"]) })
	return out
}
func (r *Recovery) RenderAudit(subs []map[string]any, env string) (any, any, []map[string]any) {
	flowInv := mapMap(r.Audit, "flow_log")
	flMeta := map[string]any{}
	if flowInv["metadata"] != nil {
		flMeta = flowInv["metadata"].(map[string]any)
	}
	arn := str(mapMap(r.Config, "flow_log")["log_group_arn"])
	if arn == "" {
		arn = str(flowInv["log_group_arn"])
	}
	fl := map[string]any{"id": first(str(flowInv["id"]), id("fl", env, "vpc")), "traffic_type": "ALL", "destination": first(str(mapMap(r.Config, "flow_log")["destination"]), str(flowInv["destination"])), "iam_policy": map[string]any{"Action": []any{"logs:CreateLogStream", "logs:PutLogEvents", "logs:DescribeLogGroups"}, "Resource": arn + ":*"}, "log_format": "${version} ${account-id} ${interface-id} ${srcaddr} ${dstaddr} ${action}", "subnet_ids": allSubnetIDs(subs), "metadata": flMeta}
	cidrs := stringAny(mapMap(r.Config, "resolver")["allowed_cidrs"])
	rules := []map[string]any{}
	for _, p := range []string{"tcp", "udp"} {
		rules = append(rules, map[string]any{"protocol": p, "from_port": 53, "to_port": 53, "cidr_blocks": cidrs, "owner": "terraform-aws-vpc-module"})
	}
	sgInv := mapMap(r.Audit, "resolver_security_group")
	sgMeta := map[string]any{}
	if sgInv["metadata"] != nil {
		sgMeta = sgInv["metadata"].(map[string]any)
	}
	sg := map[string]any{"id": first(str(sgInv["id"]), id("sg", env, "resolver-inbound")), "ingress": rules, "egress": []any{map[string]any{"protocol": "-1", "from_port": 0, "to_port": 0, "cidr_blocks": []any{r.Config["vpc_cidr"]}}}, "metadata": sgMeta}
	drift := []map[string]any{}
	for _, rule := range maps(sgInv["ingress"]) {
		if str(rule["owner"]) == "manual" {
			drift = append(drift, map[string]any{"action": "report_only", "resource": "resolver_security_group", "field": "ingress", "observed": rule, "reason": "manual rule preserved"})
		}
	}
	if str(flowInv["scope"]) != "subnet" {
		drift = append(drift, map[string]any{"action": "update_flow_log", "resource": "flow_log", "from": flowInv["scope"], "to": "subnet"})
	}
	return fl, sg, drift
}

func (r *Recovery) CheckOwner(owner string) error {
	recs, err := r.ReadJournal()
	if err != nil {
		return err
	}
	for _, rec := range recs {
		if rec.Owner != "" && rec.Owner != owner {
			return fmt.Errorf("stale owner %s cannot resume owner %s", owner, rec.Owner)
		}
		if rec.ConfigDigest != "" && rec.ConfigDigest != r.ConfigDigest() {
			return fmt.Errorf("config digest changed during recovery")
		}
	}
	return nil
}
func (r *Recovery) AppendJournal(rec JournalRecord) error {
	p := r.JournalPath()
	if err := os.MkdirAll(filepath.Dir(p), 0755); err != nil {
		return err
	}
	f, err := os.OpenFile(p, os.O_CREATE|os.O_WRONLY|os.O_APPEND, 0644)
	if err != nil {
		return err
	}
	defer f.Close()
	b, _ := json.Marshal(rec)
	_, err = f.Write(append(b, '\n'))
	return err
}
func (r *Recovery) AlreadyCommitted(owner string, st map[string]any) bool {
	current, err := r.LoadState()
	if err != nil || digestMap(current) != digestMap(st) {
		return false
	}
	recs, err := r.ReadJournal()
	if err != nil {
		return false
	}
	sd := digestMap(st)
	for _, rec := range recs {
		if rec.Event == "apply_committed" && rec.Owner == owner && rec.ConfigDigest == r.ConfigDigest() && rec.StateDigest == sd {
			return true
		}
	}
	return false
}
func (r *Recovery) ReadJournal() ([]JournalRecord, error) {
	p := r.JournalPath()
	b, err := os.ReadFile(p)
	if os.IsNotExist(err) {
		return nil, nil
	}
	if err != nil {
		return nil, err
	}
	lines := strings.Split(string(b), "\n")
	recs := []JournalRecord{}
	for i, line := range lines {
		if strings.TrimSpace(line) == "" {
			continue
		}
		var rec JournalRecord
		if e := json.Unmarshal([]byte(line), &rec); e != nil {
			if i == len(lines)-2 || i == len(lines)-1 {
				break
			}
			return nil, fmt.Errorf("journal corruption before tail")
		}
		recs = append(recs, rec)
	}
	return recs, nil
}
func (r *Recovery) RepairJournal() error {
	p := r.JournalPath()
	b, err := os.ReadFile(p)
	if os.IsNotExist(err) {
		return nil
	}
	if err != nil {
		return err
	}
	lines := strings.Split(string(b), "\n")
	keep := []string{}
	for i, line := range lines {
		if strings.TrimSpace(line) == "" {
			continue
		}
		var tmp map[string]any
		if e := json.Unmarshal([]byte(line), &tmp); e != nil {
			if i >= len(lines)-2 {
				break
			}
			return fmt.Errorf("journal corruption before tail")
		}
		keep = append(keep, line)
	}
	return os.WriteFile(p, []byte(strings.Join(keep, "\n")+"\n"), 0644)
}
func (r *Recovery) JournalPath() string {
	return filepath.Join(r.Root, "state", "recovery_journal.jsonl")
}
func (r *Recovery) StatePath() string {
	return filepath.Join(r.Root, "state", "vpc_recovered_state.json")
}
func (r *Recovery) WriteState(st map[string]any) error { return writeJSONAtomic(r.StatePath(), st) }
func (r *Recovery) LoadState() (map[string]any, error) { return readMap(r.StatePath()) }
func (r *Recovery) ConfigDigest() string               { return digestMap(r.Config) }

func readMap(path string) (map[string]any, error) {
	b, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	var m map[string]any
	if err := json.Unmarshal(b, &m); err != nil {
		return nil, err
	}
	return m, nil
}
func writeJSONAtomic(path string, obj any) error {
	if err := os.MkdirAll(filepath.Dir(path), 0755); err != nil {
		return err
	}
	b, err := json.MarshalIndent(obj, "", "  ")
	if err != nil {
		return err
	}
	b = append(b, '\n')
	tmp := path + ".tmp"
	if err := os.WriteFile(tmp, b, 0644); err != nil {
		return err
	}
	return os.Rename(tmp, path)
}
func printJSON(obj any) { b, _ := json.MarshalIndent(obj, "", "  "); fmt.Println(string(b)) }
func failJSON(j bool, err error) {
	if j {
		printJSON(map[string]any{"valid": false, "error": err.Error()})
	} else {
		fmt.Fprintln(os.Stderr, err)
	}
	os.Exit(2)
}
func die(msg string) { fmt.Fprintln(os.Stderr, msg); os.Exit(1) }
func str(v any) string {
	if v == nil {
		return ""
	}
	return fmt.Sprint(v)
}
func maps(v any) []map[string]any {
	arr, ok := v.([]any)
	if !ok {
		return nil
	}
	out := []map[string]any{}
	for _, x := range arr {
		if m, ok := x.(map[string]any); ok {
			out = append(out, m)
		}
	}
	return out
}
func mapMap(m map[string]any, k string) map[string]any {
	if x, ok := m[k].(map[string]any); ok {
		return x
	}
	return map[string]any{}
}
func stringAny(v any) []string {
	arr, ok := v.([]any)
	if !ok {
		if ss, ok := v.([]string); ok {
			return ss
		}
		return nil
	}
	out := []string{}
	for _, x := range arr {
		out = append(out, str(x))
	}
	sort.Strings(out)
	return out
}
func id(prefix string, parts ...any) string {
	ss := []string{}
	for _, p := range parts {
		s := strings.ReplaceAll(strings.ReplaceAll(str(p), "/", "_"), ".", "_")
		ss = append(ss, s)
	}
	return prefix + "-" + strings.Join(ss, "-")
}
func azSuffix(az string) string {
	if az == "" {
		return "unknown"
	}
	return az[len(az)-1:]
}
func ids(subs []map[string]any, tier string) []string {
	out := []string{}
	for _, s := range subs {
		if str(s["tier"]) == tier {
			out = append(out, str(s["id"]))
		}
	}
	sort.Strings(out)
	return out
}
func rtids(rts []map[string]any, tier string) []string {
	out := []string{}
	for _, r := range rts {
		if str(r["tier"]) == tier {
			out = append(out, str(r["id"]))
		}
	}
	sort.Strings(out)
	return out
}
func allSubnetIDs(subs []map[string]any) []string {
	out := []string{}
	for _, s := range subs {
		out = append(out, str(s["id"]))
	}
	sort.Strings(out)
	return out
}
func routeTarget(rt map[string]any, dest string) string {
	for _, r := range maps(rt["routes"]) {
		if str(r["destination"]) == dest {
			return str(r["target"])
		}
	}
	return ""
}
func first(a, b string) string {
	if a != "" {
		return a
	}
	return b
}
func digestMap(m any) string {
	b, _ := json.Marshal(m)
	h := sha256.Sum256(b)
	return hex.EncodeToString(h[:])
}
func sameStrings(a, b []string) bool {
	if len(a) != len(b) {
		return false
	}
	sort.Strings(a)
	sort.Strings(b)
	for i := range a {
		if a[i] != b[i] {
			return false
		}
	}
	return true
}
func subnetOf(child, parent *net.IPNet) bool {
	co, cb := child.Mask.Size()
	po, pb := parent.Mask.Size()
	return cb == pb && co >= po && parent.Contains(child.IP)
}
func overlaps(a, b *net.IPNet) bool { return a.Contains(b.IP) || b.Contains(a.IP) }
