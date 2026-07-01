package ec2

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
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

func insecureGroup(config Value) Value {
	return Value{
		"id":      identifier("sg", config["app"], config["environment"]),
		"ingress": []any{Value{"protocol": "tcp", "from_port": 22, "to_port": 22, "cidr_blocks": []string{"0.0.0.0/0"}}},
		"egress":  []any{Value{"protocol": "-1", "cidr_blocks": []string{"0.0.0.0/0"}}},
	}
}

func newInstance(config, template, group Value, slot int) Value {
	subnets := objects(object(config["placement"])["subnets"])
	subnet := Value{}
	if len(subnets) > 0 {
		subnet = subnets[slot%len(subnets)]
	}
	release := releaseIdentity(config)
	return Value{
		"id":                      identifier("i", config["app"], slot, stringValue(template["version"])[:10]),
		"slot":                    slot,
		"subnet_id":               subnet["id"],
		"az":                      subnet["az"],
		"public_ip_associated":    true,
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
	group := insecureGroup(config)
	desired := intValue(object(config["asg"])["desired_capacity"])
	priorRelease := stringValue(object(prior["release_identity"])["manifest_sha256"])
	sameRelease := len(prior) > 0 && priorRelease == stringValue(release["manifest_sha256"])
	priorBySlot := map[int]Value{}
	for _, item := range objects(prior["instances"]) {
		priorBySlot[intValue(item["slot"])] = item
	}
	instances := make([]any, 0, desired)
	actions := []any{}
	instanceIDs := make([]any, 0, desired)
	for slot := 0; slot < desired; slot++ {
		item, exists := priorBySlot[slot]
		if !sameRelease || !exists {
			item = newInstance(config, template, group, slot)
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
	refresh := Value{
		"strategy":               "unfenced-replace",
		"operation_id":           operation,
		"source_manifest_sha256": priorRelease,
		"target_manifest_sha256": release["manifest_sha256"],
		"status":                 "stable",
		"cursor":                 desired,
		"completed_slots":        done,
		"events":                 []any{},
	}
	subnetIDs := []any{}
	for _, subnet := range objects(object(config["placement"])["subnets"]) {
		subnetIDs = append(subnetIDs, subnet["id"])
	}
	result := Value{
		"schema_version":   "ec2sim.aws.2",
		"environment":      config["environment"],
		"application":      config["app"],
		"release_identity": release,
		"launch_template":  template,
		"security_group":   group,
		"autoscaling_group": Value{
			"name":             identifier("asg", config["app"], config["environment"]),
			"desired_capacity": desired,
			"min_size":         intValue(object(config["asg"])["min_size"]),
			"max_size":         intValue(object(config["asg"])["max_size"]),
			"subnet_ids":       subnetIDs,
			"instance_refresh": refresh,
		},
		"instances":                   instances,
		"ebs_volumes":                 []any{},
		"iam_role":                    Value{"name": identifier("role", config["app"], config["environment"]), "policy": []any{Value{"Sid": "Administrator", "Action": []string{"*"}, "Resource": "*"}}},
		"drift_report":                []any{},
		"import_report":               Value{"legacy_state": false, "moved": []any{}, "preserved_instance_ids": []any{}},
		"plan_actions":                actions,
		"journal_repair":              Value{"truncated_tail": false, "preserved_records": 0},
		"control_plane_response_lost": false,
		"outputs": Value{
			"launch_template_id":      template["id"],
			"launch_template_version": template["version"],
			"autoscaling_group_name":  identifier("asg", config["app"], config["environment"]),
			"instance_ids":            instanceIDs,
			"volume_ids":              []any{},
			"rollout_operation_id":    operation,
			"drift_report":            []any{},
		},
	}
	result["state_digest"] = hash(result, 0)
	return result, nil
}
