package main

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"strings"
)

var protected = map[string]bool{
	"module.eks.aws_eks_cluster.this[0]":             true,
	"module.eks.aws_security_group.cluster[0]":       true,
	`module.eks.aws_eks_node_group.this["system"]`:  true,
	`module.eks.aws_eks_node_group.this["apps"]`:    true,
	`module.eks.aws_eks_node_group.this["batch"]`:   true,
}

var requiredOutputs = []string{
	"cluster_endpoint",
	"cluster_security_group_id",
	"oidc_provider_arn",
	"private_subnet_ids",
	"managed_node_group_names",
	"addon_irsa_role_arns",
}

type planFile struct {
	ResourceChanges []resourceChange `json:"resource_changes"`
	Configuration   configuration    `json:"configuration"`
}

type resourceChange struct {
	Address string `json:"address"`
	Change  struct {
		Actions []string `json:"actions"`
	} `json:"change"`
}

type configuration struct {
	RootModule struct {
		Outputs map[string]any `json:"outputs"`
	} `json:"root_module"`
}

func main() {
	root, err := appRoot()
	if err != nil {
		fail(1, map[string]any{"ok": false, "error": err.Error()})
	}

	raw, err := os.ReadFile(filepath.Join(root, "fixtures", "plan.json"))
	if err != nil {
		fail(1, map[string]any{"ok": false, "error": err.Error()})
	}

	var plan planFile
	if err := json.Unmarshal(raw, &plan); err != nil {
		fail(1, map[string]any{"ok": false, "error": err.Error()})
	}

	seen := map[string]bool{}
	violations := []resourceChange{}
	adminCreates := []resourceChange{}

	for _, change := range plan.ResourceChanges {
		if contains(change.Address, "node_addon_admin") && hasAction(change.Change.Actions, "create") {
			adminCreates = append(adminCreates, change)
		}
		if !protected[change.Address] {
			continue
		}
		seen[change.Address] = true
		if len(change.Change.Actions) == 0 || !allowedActions(change.Change.Actions) {
			violations = append(violations, change)
		}
	}

	missingProtected := []string{}
	for address := range protected {
		if !seen[address] {
			missingProtected = append(missingProtected, address)
		}
	}
	sort.Strings(missingProtected)

	if len(violations) > 0 || len(adminCreates) > 0 || len(missingProtected) > 0 {
		fail(2, map[string]any{
			"ok":                false,
			"violations":        violations,
			"admin_creates":     adminCreates,
			"missing_protected": missingProtected,
		})
	}

	missingOutputs := []string{}
	outputs := plan.Configuration.RootModule.Outputs
	for _, name := range requiredOutputs {
		if _, ok := outputs[name]; !ok {
			missingOutputs = append(missingOutputs, name)
		}
	}
	if len(missingOutputs) > 0 {
		fail(3, map[string]any{"ok": false, "missing_outputs": missingOutputs})
	}

	fmt.Println(`{"ok":true}`)
}

func appRoot() (string, error) {
	if env := os.Getenv("APP_ROOT"); env != "" {
		return env, nil
	}
	exe, err := os.Executable()
	if err != nil {
		return "", err
	}
	return filepath.Dir(filepath.Dir(exe)), nil
}

func allowedActions(actions []string) bool {
	allowed := map[string]bool{"no-op": true, "read": true, "update": true}
	for _, action := range actions {
		if !allowed[action] {
			return false
		}
	}
	return true
}

func hasAction(actions []string, target string) bool {
	for _, action := range actions {
		if action == target {
			return true
		}
	}
	return false
}

func contains(s, substr string) bool {
	return strings.Contains(s, substr)
}

func fail(code int, payload map[string]any) {
	encoded, err := json.Marshal(payload)
	if err != nil {
		fmt.Fprintf(os.Stderr, `{"ok":false,"error":%q}`+"\n", err.Error())
		os.Exit(code)
	}
	fmt.Fprintln(os.Stderr, string(encoded))
	os.Exit(code)
}
