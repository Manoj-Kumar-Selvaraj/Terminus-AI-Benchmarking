package main

import (
	"encoding/json"
	"fmt"
	"strconv"
)

func stringValue(value any) string {
	switch typed := value.(type) {
	case string:
		return typed
	case nil:
		return ""
	default:
		return fmt.Sprint(typed)
	}
}

func intValue(value any, fallback int) int {
	switch typed := value.(type) {
	case float64:
		return int(typed)
	case float32:
		return int(typed)
	case int:
		return typed
	case int64:
		return int(typed)
	case json.Number:
		parsed, err := typed.Int64()
		if err == nil {
			return int(parsed)
		}
	case string:
		parsed, err := strconv.Atoi(typed)
		if err == nil {
			return parsed
		}
	}
	return fallback
}

func cloneMap(input map[string]any) map[string]any {
	data, _ := json.Marshal(input)
	var output map[string]any
	_ = json.Unmarshal(data, &output)
	return output
}

func loadRuntime() (map[string]any, map[string]any, map[string]any, error) {
	mapping := map[string]any{}
	queues := map[string]any{}
	policy := map[string]any{}
	if err := loadJSON(configPath("event_source_mapping.json"), &mapping); err != nil {
		return nil, nil, nil, err
	}
	if err := loadJSON(configPath("queues.json"), &queues); err != nil {
		return nil, nil, nil, err
	}
	if err := loadJSON(configPath("lambda_role_policy.json"), &policy); err != nil {
		return nil, nil, nil, err
	}
	return mapping, queues, policy, nil
}

func mappingProbe() (map[string]any, error) {
	mapping, queues, _, err := loadRuntime()
	if err != nil {
		return nil, err
	}
	return activeMapping(mapping, queues), nil
}

func iamProbe() (map[string]any, error) {
	_, queues, policy, err := loadRuntime()
	if err != nil {
		return nil, err
	}
	queueARN := stringValue(queues["expected_active_queue_arn"])
	return map[string]any{
		"queue_arn":           queueARN,
		"decisions":           requiredSQSDecisions(policy, queueARN),
		"old_queue_receive":   decide(policy, "sqs:ReceiveMessage", stringValue(queues["old_queue_arn"])),
		"has_broad_sqs_grant": hasBroadSQSGrant(policy),
		"has_log_permissions": hasLogPermissions(policy),
	}, nil
}

func eventRecords(messages []map[string]any) []map[string]any {
	records := make([]map[string]any, 0, len(messages))
	for _, message := range messages {
		cloned := cloneMap(message)
		attrs, _ := cloned["attributes"].(map[string]any)
		if attrs == nil {
			attrs = map[string]any{}
		}
		count := intValue(attrs["ApproximateReceiveCount"], 0) + 1
		attrs["ApproximateReceiveCount"] = strconv.Itoa(count)
		cloned["attributes"] = attrs
		records = append(records, cloned)
	}
	return records
}

func messageReason(message map[string]any) string {
	bodyText := stringValue(message["body"])
	body := map[string]any{}
	if err := json.Unmarshal([]byte(bodyText), &body); err != nil {
		return "MALFORMED_JSON"
	}
	poison, _ := body["poison"].(bool)
	if poison {
		if reason := stringValue(body["failure_reason"]); reason != "" {
			return reason
		}
		return "POISON_MESSAGE"
	}
	return "PROCESSING_FAILED"
}

func messageSlice(value any) []map[string]any {
	raw, _ := value.([]any)
	messages := make([]map[string]any, 0, len(raw))
	for _, item := range raw {
		if message, ok := item.(map[string]any); ok {
			messages = append(messages, cloneMap(message))
		}
	}
	return messages
}

func simulateBatch(batchFile string, cycles int) (map[string]any, error) {
	mapping, queues, policy, err := loadRuntime()
	if err != nil {
		return nil, err
	}
	mapInfo := activeMapping(mapping, queues)
	batch := map[string]any{}
	if err := loadJSON(batchFile, &batch); err != nil {
		return nil, err
	}
	redrive := map[string]any{}
	if err := loadJSON(configPath("redrive_policy.json"), &redrive); err != nil {
		return nil, err
	}
	queueARN := stringValue(batch["queue_arn"])
	if queueARN == "" {
		queueARN = stringValue(queues["expected_active_queue_arn"])
	}
	result := map[string]any{
		"mapping":               mapInfo,
		"queue_arn":             queueARN,
		"cycles":                []any{},
		"access_denied":         false,
		"access_denied_actions": []any{},
		"delivered_message_ids": []any{},
		"deleted_message_ids":   []any{},
		"failed_message_ids":    []any{},
		"receive_counts":        map[string]any{},
		"dlq_message_ids":       []any{},
	}

	expectedARN := stringValue(queues["expected_active_queue_arn"])
	required := requiredSQSDecisions(policy, expectedARN)
	denied := []any{}
	for _, action := range requiredSQSActions {
		if stringValue(required[action]) != "allowed" {
			denied = append(denied, action)
		}
	}
	if len(denied) > 0 {
		ledger, loadErr := loadLedger()
		if loadErr != nil {
			return nil, loadErr
		}
		dlq, loadErr := loadDLQ()
		if loadErr != nil {
			return nil, loadErr
		}
		result["access_denied"] = true
		result["access_denied_actions"] = denied
		result["ledger_entries"] = ledger
		result["dlq_entries"] = dlq
		return result, nil
	}

	active, _ := mapInfo["active"].(bool)
	if !active || queueARN != expectedARN {
		ledger, loadErr := loadLedger()
		if loadErr != nil {
			return nil, loadErr
		}
		dlq, loadErr := loadDLQ()
		if loadErr != nil {
			return nil, loadErr
		}
		result["ledger_entries"] = ledger
		result["dlq_entries"] = dlq
		return result, nil
	}

	messages := messageSlice(batch["messages"])
	maxReceive := intValue(redrive["max_receive_count"], 3)
	deleted := map[string]bool{}
	dlqed := map[string]bool{}
	currentDLQ, err := loadDLQ()
	if err != nil {
		return nil, err
	}
	for _, entry := range currentDLQ {
		if original := stringValue(entry["original_message_id"]); original != "" {
			dlqed[original] = true
		}
	}

	for cycle := 0; cycle < cycles; cycle++ {
		available := make([]map[string]any, 0, len(messages))
		for _, message := range messages {
			mid := stringValue(message["messageId"])
			if !deleted[mid] && !dlqed[mid] {
				available = append(available, message)
			}
		}
		cyclesOut := result["cycles"].([]any)
		if len(available) == 0 {
			result["cycles"] = append(cyclesOut, map[string]any{
				"delivered": []any{}, "failed": []any{}, "deleted": []any{},
			})
			continue
		}
		batchSize := intValue(mapping["batch_size"], 10)
		if batchSize > len(available) {
			batchSize = len(available)
		}
		delivered := available[:batchSize]
		records := eventRecords(delivered)
		receiveCounts := result["receive_counts"].(map[string]any)
		for index, record := range records {
			original := delivered[index]
			attrs := record["attributes"].(map[string]any)
			originalAttrs, _ := original["attributes"].(map[string]any)
			if originalAttrs == nil {
				originalAttrs = map[string]any{}
			}
			originalAttrs["ApproximateReceiveCount"] = attrs["ApproximateReceiveCount"]
			original["attributes"] = originalAttrs
			receiveCounts[stringValue(original["messageId"])] = intValue(originalAttrs["ApproximateReceiveCount"], 0)
		}

		rawRecords := make([]any, 0, len(records))
		for _, record := range records {
			rawRecords = append(rawRecords, record)
		}
		response, err := handleBatch(map[string]any{"Records": rawRecords})
		if err != nil {
			return nil, err
		}
		failedIDs := map[string]bool{}
		if rawFailures, ok := response["batchItemFailures"].([]any); ok {
			for _, rawFailure := range rawFailures {
				failure, ok := rawFailure.(map[string]any)
				if !ok {
					continue
				}
				failedIDs[stringValue(failure["itemIdentifier"])] = true
			}
		}

		cycleDeleted := []any{}
		cycleFailed := []any{}
		deliveredIDs := make([]any, 0, len(delivered))
		for _, message := range delivered {
			mid := stringValue(message["messageId"])
			deliveredIDs = append(deliveredIDs, mid)
			result["delivered_message_ids"] = append(result["delivered_message_ids"].([]any), mid)
			if failedIDs[mid] {
				result["failed_message_ids"] = append(result["failed_message_ids"].([]any), mid)
				cycleFailed = append(cycleFailed, mid)
				attrs, _ := message["attributes"].(map[string]any)
				receiveCount := intValue(attrs["ApproximateReceiveCount"], 0)
				if receiveCount >= maxReceive {
					var eventID any
					body := map[string]any{}
					if err := json.Unmarshal([]byte(stringValue(message["body"])), &body); err == nil {
						eventID = body["business_event_id"]
					}
					if err := appendDLQEntry(map[string]any{
						"message_id":          "dlq-" + mid,
						"original_message_id": mid,
						"business_event_id":   eventID,
						"source_queue_arn":    queueARN,
						"failure_reason":      messageReason(message),
						"receive_count":       receiveCount,
					}); err != nil {
						return nil, err
					}
					dlqed[mid] = true
					result["dlq_message_ids"] = append(result["dlq_message_ids"].([]any), mid)
				}
			} else {
				deleted[mid] = true
				result["deleted_message_ids"] = append(result["deleted_message_ids"].([]any), mid)
				cycleDeleted = append(cycleDeleted, mid)
			}
		}
		result["cycles"] = append(cyclesOut, map[string]any{
			"delivered": deliveredIDs,
			"failed":    cycleFailed,
			"deleted":   cycleDeleted,
		})
	}

	ledger, err := loadLedger()
	if err != nil {
		return nil, err
	}
	dlq, err := loadDLQ()
	if err != nil {
		return nil, err
	}
	result["ledger_entries"] = ledger
	result["dlq_entries"] = dlq
	return result, nil
}
