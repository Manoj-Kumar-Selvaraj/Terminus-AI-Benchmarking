package delivery

import (
	"bytes"
	"encoding/json"
	"fmt"
	"sort"
)

func BuildModernPayload(eventType string, fields map[string]string) ([]byte, error) {
	body := map[string]any{
		"event_type":     eventType,
		"schema_version": "2",
		"trace_id":       fields["trace_id"],
		"fields":         fields,
	}
	return json.Marshal(body)
}

func BuildLegacyPayload(eventType string, fields map[string]string) ([]byte, error) {
	keys := make([]string, 0, len(fields))
	for key := range fields {
		keys = append(keys, key)
	}
	sort.Strings(keys)
	var buf bytes.Buffer
	buf.WriteString("{")
	for i, key := range keys {
		if i > 0 {
			buf.WriteString(",")
		}
		buf.WriteString(fmt.Sprintf("%q:%q", key, fields[key]))
	}
	buf.WriteString(fmt.Sprintf(",\"event_type\":%q", eventType))
	buf.WriteString("}")
	return buf.Bytes(), nil
}

func IsLegacyClient(clientID string) bool {
	return clientID == "legacy-v1"
}
