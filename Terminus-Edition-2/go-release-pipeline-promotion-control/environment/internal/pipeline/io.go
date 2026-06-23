package pipeline

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
)

func LoadScenario(path string) (Scenario, error) {
	var scenario Scenario
	data, err := os.ReadFile(path)
	if err != nil {
		return scenario, err
	}
	if err := json.Unmarshal(data, &scenario); err != nil {
		return scenario, err
	}
	if scenario.Branch == "" || scenario.CommitSHA == "" || scenario.BuildNumber == "" || scenario.Environment == "" {
		return scenario, fmt.Errorf("scenario is missing branch, commit_sha, build_number, or environment")
	}
	return scenario, nil
}

func writeJSON(path string, value any) error {
	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
		return err
	}
	data, err := json.MarshalIndent(value, "", "  ")
	if err != nil {
		return err
	}
	data = append(data, '\n')
	return os.WriteFile(path, data, 0o644)
}

func readHistory(path string) (ReleaseHistory, error) {
	var history ReleaseHistory
	data, err := os.ReadFile(path)
	if err != nil {
		return history, err
	}
	if err := json.Unmarshal(data, &history); err != nil {
		return history, err
	}
	if history.SchemaVersion == "" || history.Releases == nil {
		return history, fmt.Errorf("release history is missing schema_version or releases")
	}
	return history, nil
}
