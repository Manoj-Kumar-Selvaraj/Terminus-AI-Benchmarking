package main

func activeMapping(mapping, queues map[string]any) map[string]any {
	enabled, _ := mapping["enabled"].(bool)
	expectedARN := stringValue(queues["expected_active_queue_arn"])
	sourceARN := stringValue(mapping["event_source_arn"])
	responseTypes := mapping["function_response_types"]
	if responseTypes == nil {
		responseTypes = []any{}
	}
	return map[string]any{
		"uuid":                      mapping["uuid"],
		"enabled":                   enabled,
		"active":                    enabled && sourceARN == expectedARN,
		"function_name":             mapping["function_name"],
		"event_source_arn":          mapping["event_source_arn"],
		"expected_event_source_arn": queues["expected_active_queue_arn"],
		"old_queue_arn":             queues["old_queue_arn"],
		"batch_size":                mapping["batch_size"],
		"function_response_types":   responseTypes,
	}
}
