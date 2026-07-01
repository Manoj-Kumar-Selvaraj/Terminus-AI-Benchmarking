package ec2

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"sort"
	"strconv"
	"strings"
)

type Value map[string]any

func canonical(value any) []byte {
	data, _ := json.Marshal(value)
	return data
}

func hash(value any, length int) string {
	sum := sha256.Sum256(canonical(value))
	encoded := hex.EncodeToString(sum[:])
	if length > 0 {
		return encoded[:length]
	}
	return encoded
}

func object(value any) Value {
	if result, ok := value.(Value); ok {
		return result
	}
	if result, ok := value.(map[string]any); ok {
		return result
	}
	return Value{}
}

func objects(value any) []Value {
	list, _ := value.([]any)
	result := make([]Value, 0, len(list))
	for _, item := range list {
		result = append(result, object(item))
	}
	return result
}

func stringList(value any) []string {
	list, _ := value.([]any)
	result := make([]string, 0, len(list))
	for _, item := range list {
		result = append(result, stringValue(item))
	}
	return result
}

func stringValue(value any) string {
	if value == nil {
		return ""
	}
	if result, ok := value.(string); ok {
		return result
	}
	return fmt.Sprint(value)
}

func intValue(value any) int {
	switch typed := value.(type) {
	case int:
		return typed
	case float64:
		return int(typed)
	case json.Number:
		parsed, _ := typed.Int64()
		return int(parsed)
	case string:
		parsed, _ := strconv.Atoi(typed)
		return parsed
	default:
		return 0
	}
}

func boolValue(value any) bool {
	result, _ := value.(bool)
	return result
}

func required(value any, name string, errors *[]string) {
	if value == nil || value == "" {
		*errors = append(*errors, name+" is required")
	}
}

func identifier(prefix string, parts ...any) string {
	values := make([]string, 0, len(parts))
	for _, part := range parts {
		value := strings.ReplaceAll(stringValue(part), "/", "_")
		value = strings.ReplaceAll(value, ":", "_")
		values = append(values, value)
	}
	return prefix + "-" + strings.Join(values, "-")
}

func manifestPayload(artifact Value) Value {
	result := Value{}
	for _, key := range []string{"manifest_version", "ami_id", "ami_owner_account_id", "architecture", "commit_sha", "build_id", "user_data_sha256"} {
		result[key] = artifact[key]
	}
	return result
}

func releaseIdentity(config Value) Value {
	artifact := object(config["release_artifact"])
	result := manifestPayload(artifact)
	result["manifest_sha256"] = artifact["manifest_sha256"]
	return result
}

func ValidateConfig(config Value) error {
	errors := []string{}
	if stringValue(config["schema_version"]) != "ec2-module-config.v2" {
		errors = append(errors, "schema_version must be ec2-module-config.v2")
	}
	artifact := object(config["release_artifact"])
	for _, field := range []string{"manifest_version", "ami_id", "ami_owner_account_id", "architecture", "commit_sha", "build_id", "user_data_sha256", "manifest_sha256"} {
		required(artifact[field], "release_artifact."+field, &errors)
	}
	if len(errors) == 0 {
		if stringValue(artifact["manifest_sha256"]) != hash(manifestPayload(artifact), 0) {
			errors = append(errors, "release_artifact.manifest_sha256 does not match canonical manifest")
		}
		images := object(object(config["ami_catalog"])["images"])
		image, found := images[stringValue(artifact["ami_id"])]
		if !found {
			errors = append(errors, "release_artifact.ami_id is absent from ami_catalog.images")
		} else {
			candidate := object(image)
			if candidate["owner_account_id"] != artifact["ami_owner_account_id"] {
				errors = append(errors, "release_artifact.ami_owner_account_id does not match catalog owner")
			}
			if candidate["architecture"] != artifact["architecture"] {
				errors = append(errors, "release_artifact.architecture does not match catalog architecture")
			}
			if stringValue(candidate["state"]) != "available" {
				errors = append(errors, "release_artifact.ami_id must be available")
			}
			if boolValue(candidate["deprecated"]) {
				errors = append(errors, "release_artifact.ami_id must not be deprecated")
			}
		}
	}
	placement := object(config["placement"])
	seenIDs, seenAZs := map[string]bool{}, map[string]bool{}
	for _, subnet := range objects(placement["subnets"]) {
		id, az := stringValue(subnet["id"]), stringValue(subnet["az"])
		if stringValue(subnet["tier"]) != "private_app" {
			errors = append(errors, fmt.Sprintf("subnet %s must have tier private_app", id))
		}
		if subnet["account_id"] != config["account_id"] {
			errors = append(errors, fmt.Sprintf("subnet %s must belong to configured account", id))
		}
		if !strings.HasPrefix(id, "subnet-") {
			errors = append(errors, "subnet id must start with subnet-")
		}
		if !strings.HasPrefix(az, stringValue(config["region"])) {
			errors = append(errors, fmt.Sprintf("subnet %s has invalid availability zone", id))
		}
		if seenIDs[id] {
			errors = append(errors, "duplicate subnet id "+id)
		}
		if seenAZs[az] {
			errors = append(errors, "duplicate availability zone "+az)
		}
		seenIDs[id], seenAZs[az] = true, true
	}
	minimumAZs := intValue(placement["minimum_azs"])
	if len(seenAZs) < minimumAZs {
		errors = append(errors, fmt.Sprintf("placement requires at least %d unique availability zones", minimumAZs))
	}
	network := object(config["network"])
	alb, resolver := stringValue(network["alb_security_group_id"]), stringValue(network["resolver_security_group_id"])
	prefixLists := stringList(network["endpoint_prefix_lists"])
	if !strings.HasPrefix(alb, "sg-") {
		errors = append(errors, "network.alb_security_group_id must start with sg-")
	}
	if !strings.HasPrefix(resolver, "sg-") {
		errors = append(errors, "network.resolver_security_group_id must start with sg-")
	}
	if len(prefixLists) == 0 {
		errors = append(errors, "network.endpoint_prefix_lists is required")
	}
	seenPrefixes := map[string]bool{}
	for _, prefix := range prefixLists {
		if seenPrefixes[prefix] {
			errors = append(errors, "network.endpoint_prefix_lists contains duplicates")
		}
		seenPrefixes[prefix] = true
		if !strings.HasPrefix(prefix, "pl-") {
			errors = append(errors, "network.endpoint_prefix_lists entries must start with pl-")
		}
	}
	port := intValue(config["service_port"])
	if port < 1 || port > 65535 {
		errors = append(errors, "service_port must be between 1 and 65535")
	}
	if len(errors) > 0 {
		return fmt.Errorf("%s", strings.Join(errors, "; "))
	}
	return nil
}

func launchTemplate(config Value) Value {
	release := releaseIdentity(config)
	body := Value{
		"ami_id":           release["ami_id"],
		"architecture":     release["architecture"],
		"instance_type":    config["instance_type"],
		"user_data_sha256": release["user_data_sha256"],
		"metadata_options": Value{"http_tokens": "optional", "http_endpoint": "enabled", "http_put_response_hop_limit": 2},
		"provenance":       Value{"commit_sha": release["commit_sha"], "build_id": release["build_id"], "manifest_sha256": release["manifest_sha256"]},
	}
	return Value{
		"id":               identifier("lt", config["app"], config["environment"]),
		"version":          hash(body, 20),
		"ami_id":           body["ami_id"],
		"architecture":     body["architecture"],
		"instance_type":    body["instance_type"],
		"user_data_sha256": body["user_data_sha256"],
		"metadata_options": body["metadata_options"],
		"provenance":       body["provenance"],
		"tags": Value{
			"Application":           config["app"],
			"Environment":           config["environment"],
			"ManagedBy":             "terraform-aws-ec2-module",
			"ReleaseManifestSha256": release["manifest_sha256"],
		},
	}
}

func stableOperationID(config Value, target string, desired int) string {
	return "stable-" + hash(Value{"app": config["app"], "environment": config["environment"], "target_manifest": target, "desired_capacity": desired}, 18)
}

func securityGroup(config Value) Value {
	network := object(config["network"])
	port := intValue(config["service_port"])
	prefixes := stringList(network["endpoint_prefix_lists"])
	sort.Strings(prefixes)
	return Value{
		"id":      identifier("sg", config["app"], config["environment"]),
		"ingress": []any{Value{"protocol": "tcp", "from_port": port, "to_port": port, "source_security_group_id": network["alb_security_group_id"]}},
		"egress": []any{
			Value{"protocol": "tcp", "from_port": 443, "to_port": 443, "prefix_list_ids": prefixes},
			Value{"protocol": "udp", "from_port": 53, "to_port": 53, "source_security_group_id": network["resolver_security_group_id"]},
			Value{"protocol": "tcp", "from_port": 53, "to_port": 53, "source_security_group_id": network["resolver_security_group_id"]},
		},
	}
}

func eligibleSubnets(config Value) []Value {
	result := objects(object(config["placement"])["subnets"])
	sort.Slice(result, func(i, j int) bool {
		left, right := stringValue(result[i]["az"]), stringValue(result[j]["az"])
		if left == right {
			return stringValue(result[i]["id"]) < stringValue(result[j]["id"])
		}
		return left < right
	})
	return result
}

func placementBySlot(config Value, desired int, prior []Value) map[int]Value {
	eligible := eligibleSubnets(config)
	eligibleIDs := map[string]Value{}
	for _, subnet := range eligible {
		eligibleIDs[stringValue(subnet["id"])] = subnet
	}
	priorBySlot := map[int]Value{}
	for _, item := range prior {
		priorBySlot[intValue(item["slot"])] = item
	}
	result := map[int]Value{}
	for slot := 0; slot < desired; slot++ {
		if item, ok := priorBySlot[slot]; ok {
			if subnet, eligible := eligibleIDs[stringValue(item["subnet_id"])]; eligible {
				result[slot] = subnet
				continue
			}
		}
		result[slot] = eligible[slot%len(eligible)]
	}
	return result
}

func newInstance(config, template, group Value, slot int, subnet Value) Value {
	release := releaseIdentity(config)
	return Value{
		"id":                      identifier("i", config["app"], slot, stringValue(template["version"])[:10]),
		"slot":                    slot,
		"subnet_id":               subnet["id"],
		"az":                      subnet["az"],
		"public_ip_associated":    false,
		"security_group_id":       group["id"],
		"launch_template_version": template["version"],
		"ami_id":                  template["ami_id"],
		"state":                   "running",
		"health":                  "healthy",
		"tags": Value{
			"Application":           config["app"],
			"Environment":           config["environment"],
			"Slot":                  strconv.Itoa(slot),
			"CommitSha":             release["commit_sha"],
			"BuildId":               release["build_id"],
			"ReleaseManifestSha256": release["manifest_sha256"],
		},
	}
}

func Render(config Value, prior Value) (Value, error) {
	if err := ValidateConfig(config); err != nil {
		return nil, err
	}
	release := releaseIdentity(config)
	template := launchTemplate(config)
	group := securityGroup(config)
	desired := intValue(object(config["asg"])["desired_capacity"])
	priorRelease := stringValue(object(prior["release_identity"])["manifest_sha256"])
	sameRelease := len(prior) > 0 && priorRelease == stringValue(release["manifest_sha256"])
	priorInstances := objects(prior["instances"])
	priorBySlot := map[int]Value{}
	for _, item := range priorInstances {
		priorBySlot[intValue(item["slot"])] = item
	}
	placements := placementBySlot(config, desired, priorInstances)
	instances := make([]any, 0, desired)
	actions := []any{}
	instanceIDs := make([]any, 0, desired)
	for slot := 0; slot < desired; slot++ {
		item, exists := priorBySlot[slot]
		if !sameRelease || !exists {
			item = newInstance(config, template, group, slot, placements[slot])
			action := "create"
			if exists {
				action = "rolling_replace"
			}
			actions = append(actions, Value{"action": action, "slot": slot, "instance_id": item["id"]})
		} else {
			actions = append(actions, Value{"action": "no_op", "slot": slot, "instance_id": item["id"]})
		}
		instances = append(instances, item)
		instanceIDs = append(instanceIDs, item["id"])
	}
	for slot, item := range priorBySlot {
		if slot >= desired {
			actions = append(actions, Value{"action": "scale_in", "slot": slot, "instance_id": item["id"]})
		}
	}
	done := make([]any, desired)
	for slot := 0; slot < desired; slot++ {
		done[slot] = slot
	}
	operation := stableOperationID(config, stringValue(release["manifest_sha256"]), desired)
	refresh := Value{"strategy": "unfenced-replace", "operation_id": operation, "source_manifest_sha256": priorRelease, "target_manifest_sha256": release["manifest_sha256"], "status": "stable", "cursor": desired, "completed_slots": done, "events": []any{}}
	subnetIDs := make([]any, 0)
	for _, subnet := range eligibleSubnets(config) {
		subnetIDs = append(subnetIDs, subnet["id"])
	}
	result := Value{
		"schema_version":              "ec2sim.aws.2",
		"environment":                 config["environment"],
		"application":                 config["app"],
		"release_identity":            release,
		"launch_template":             template,
		"security_group":              group,
		"autoscaling_group":           Value{"name": identifier("asg", config["app"], config["environment"]), "desired_capacity": desired, "min_size": intValue(object(config["asg"])["min_size"]), "max_size": intValue(object(config["asg"])["max_size"]), "subnet_ids": subnetIDs, "instance_refresh": refresh},
		"instances":                   instances,
		"ebs_volumes":                 []any{},
		"iam_role":                    Value{"name": identifier("role", config["app"], config["environment"]), "policy": []any{Value{"Sid": "Administrator", "Action": []string{"*"}, "Resource": "*"}}},
		"drift_report":                []any{},
		"import_report":               Value{"legacy_state": false, "moved": []any{}, "preserved_instance_ids": []any{}},
		"plan_actions":                actions,
		"journal_repair":              Value{"truncated_tail": false, "preserved_records": 0},
		"control_plane_response_lost": false,
		"outputs":                     Value{"launch_template_id": template["id"], "launch_template_version": template["version"], "autoscaling_group_name": identifier("asg", config["app"], config["environment"]), "instance_ids": instanceIDs, "volume_ids": []any{}, "rollout_operation_id": operation, "drift_report": []any{}},
	}
	result["state_digest"] = hash(result, 0)
	return result, nil
}
