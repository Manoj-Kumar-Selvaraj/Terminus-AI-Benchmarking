package cli

import (
	"encoding/json"
	"errors"
	"os"
	"strings"
)

func ReadGatewayMap(path string) (map[string]string, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	var out map[string]string
	if err := json.Unmarshal(data, &out); err != nil {
		return nil, err
	}
	if len(out) == 0 {
		return nil, errors.New("gateway map is empty")
	}
	for region, endpoint := range out {
		if strings.TrimSpace(region) == "" || strings.TrimSpace(endpoint) == "" {
			return nil, errors.New("gateway map contains empty entry")
		}
	}
	return out, nil
}
