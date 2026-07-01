package main

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
)

func loadJSON(path string, out any) error {
	data, err := os.ReadFile(path)
	if err != nil {
		return err
	}
	if err := json.Unmarshal(data, out); err != nil {
		return fmt.Errorf("decode %s: %w", path, err)
	}
	return nil
}

func saveJSON(path string, value any) error {
	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
		return err
	}
	data, err := json.MarshalIndent(value, "", "  ")
	if err != nil {
		return err
	}
	data = append(data, '\n')
	tmp := path + ".tmp"
	if err := os.WriteFile(tmp, data, 0o644); err != nil {
		return err
	}
	return os.Rename(tmp, path)
}

func loadJSONArray(path string) ([]map[string]any, error) {
	var entries []map[string]any
	if _, err := os.Stat(path); os.IsNotExist(err) {
		return []map[string]any{}, nil
	}
	if err := loadJSON(path, &entries); err != nil {
		return nil, err
	}
	if entries == nil {
		entries = []map[string]any{}
	}
	return entries, nil
}
