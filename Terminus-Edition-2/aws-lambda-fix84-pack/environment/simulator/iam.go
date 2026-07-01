package main

import (
	"regexp"
	"strings"
)

var requiredSQSActions = []string{
	"sqs:ReceiveMessage",
	"sqs:DeleteMessage",
	"sqs:ChangeMessageVisibility",
	"sqs:GetQueueAttributes",
}

func asStrings(value any) []string {
	switch typed := value.(type) {
	case nil:
		return []string{}
	case string:
		return []string{typed}
	case []any:
		result := make([]string, 0, len(typed))
		for _, item := range typed {
			result = append(result, stringValue(item))
		}
		return result
	case []string:
		return append([]string(nil), typed...)
	default:
		return []string{stringValue(typed)}
	}
}

func globMatch(pattern, value string) bool {
	var b strings.Builder
	b.WriteString("^")
	for _, r := range pattern {
		switch r {
		case '*':
			b.WriteString(".*")
		case '?':
			b.WriteString(".")
		default:
			b.WriteString(regexp.QuoteMeta(string(r)))
		}
	}
	b.WriteString("$")
	matched, err := regexp.MatchString(b.String(), value)
	return err == nil && matched
}

func matches(patterns []string, value string) bool {
	for _, pattern := range patterns {
		if globMatch(pattern, value) {
			return true
		}
	}
	return false
}

func statements(policy map[string]any) []map[string]any {
	raw, _ := policy["Statement"].([]any)
	result := make([]map[string]any, 0, len(raw))
	for _, item := range raw {
		if statement, ok := item.(map[string]any); ok {
			result = append(result, statement)
		}
	}
	return result
}

func decide(policy map[string]any, action, resource string) string {
	decision := "implicitDeny"
	for _, statement := range statements(policy) {
		actions := asStrings(statement["Action"])
		resources := asStrings(statement["Resource"])
		if !matches(actions, action) || !matches(resources, resource) {
			continue
		}
		switch stringValue(statement["Effect"]) {
		case "Deny":
			return "explicitDeny"
		case "Allow":
			decision = "allowed"
		}
	}
	return decision
}

func requiredSQSDecisions(policy map[string]any, queueARN string) map[string]any {
	decisions := make(map[string]any, len(requiredSQSActions))
	for _, action := range requiredSQSActions {
		decisions[action] = decide(policy, action, queueARN)
	}
	return decisions
}

func hasBroadSQSGrant(policy map[string]any) bool {
	for _, statement := range statements(policy) {
		if stringValue(statement["Effect"]) != "Allow" {
			continue
		}
		actions := asStrings(statement["Action"])
		resources := asStrings(statement["Resource"])
		for _, action := range actions {
			if action == "*" || action == "sqs:*" {
				return true
			}
		}
		wildcardResource := false
		for _, resource := range resources {
			if resource == "*" {
				wildcardResource = true
				break
			}
		}
		if wildcardResource {
			for _, action := range actions {
				if action == "*" || strings.HasPrefix(action, "sqs:") {
					return true
				}
			}
		}
	}
	return false
}

func hasLogPermissions(policy map[string]any) bool {
	needed := []string{"logs:CreateLogStream", "logs:PutLogEvents"}
	for _, action := range needed {
		found := false
		for _, statement := range statements(policy) {
			if stringValue(statement["Effect"]) == "Allow" && matches(asStrings(statement["Action"]), action) {
				found = true
				break
			}
		}
		if !found {
			return false
		}
	}
	return true
}
