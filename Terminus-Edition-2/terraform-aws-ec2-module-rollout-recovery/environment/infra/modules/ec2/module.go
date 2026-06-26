package ec2

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
)

type Value map[string]any

func digest(value any) string {
	data, _ := json.Marshal(value)
	sum := sha256.Sum256(data)
	return hex.EncodeToString(sum[:])
}

func text(value any) string {
	if result, ok := value.(string); ok {
		return result
	}
	return fmt.Sprint(value)
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

func ValidateConfig(config Value) error {
	if text(config["schema_version"]) != "ec2-module-config.v2" {
		return fmt.Errorf("schema_version must be ec2-module-config.v2")
	}
	return nil
}

func Render(config Value, prior Value) (Value, error) {
	if err := ValidateConfig(config); err != nil {
		return nil, err
	}
	artifact := object(config["release_artifact"])
	app, environment := text(config["app"]), text(config["environment"])
	release := Value{
		"manifest_version": artifact["manifest_version"],
		"ami_id":             "ami-latest",
		"architecture":       "unknown",
		"commit_sha":         "HEAD",
		"build_id":           "latest",
		"user_data_sha256":   "latest-bootstrap",
		"manifest_sha256":    "mutable-latest",
	}
	template := Value{
		"id":                 "lt-" + app,
		"version":            "latest",
		"ami_id":             release["ami_id"],
		"architecture":       release["architecture"],
		"instance_type":      config["instance_type"],
		"user_data_sha256":   release["user_data_sha256"],
		"metadata_options":   Value{"http_tokens": "optional", "http_endpoint": "enabled", "http_put_response_hop_limit": 2},
		"provenance":         Value{"commit_sha": "HEAD", "build_id": "latest", "manifest_sha256": "mutable-latest"},
	}
	result := Value{
		"schema_version":    "ec2sim.aws.2",
		"environment":       environment,
		"application":       app,
		"release_identity":  release,
		"launch_template":   template,
		"security_group":    Value{"id": "sg-" + app + "-" + environment, "ingress": []any{Value{"protocol": "tcp", "from_port": 22, "to_port": 22, "cidr_blocks": []string{"0.0.0.0/0"}}}},
		"autoscaling_group": Value{"name": "asg-" + app + "-" + environment, "instance_refresh": Value{"status": "stable", "events": []any{}}},
		"instances":         []any{},
		"ebs_volumes":       []any{},
		"iam_role":          Value{"name": "role-" + app + "-" + environment, "policy": []any{Value{"Sid": "Administrator", "Action": []string{"*"}, "Resource": "*"}}},
		"drift_report":      []any{},
		"import_report":     Value{"legacy_state": false, "moved": []any{}, "preserved_instance_ids": []any{}},
		"plan_actions":      []any{},
		"journal_repair":    Value{"truncated_tail": false, "preserved_records": 0},
		"control_plane_response_lost": false,
		"outputs": Value{"launch_template_id": template["id"], "launch_template_version": template["version"], "autoscaling_group_name": "asg-" + app + "-" + environment, "instance_ids": []any{}, "volume_ids": []any{}, "rollout_operation_id": nil, "drift_report": []any{}},
	}
	result["state_digest"] = digest(result)
	return result, nil
}
