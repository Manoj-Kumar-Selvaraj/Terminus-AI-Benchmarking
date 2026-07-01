package main

import (
	"bytes"
	"encoding/json"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
)

func handleBatch(event map[string]any) (map[string]any, error) {
	input, err := json.Marshal(event)
	if err != nil {
		return nil, err
	}
	invoke := filepath.Join(appRoot(), "handler", "invoke.mjs")
	cmd := exec.Command("node", invoke)
	cmd.Dir = appRoot()
	cmd.Env = os.Environ()
	cmd.Stdin = bytes.NewReader(input)
	var stdout bytes.Buffer
	var stderr bytes.Buffer
	cmd.Stdout = &stdout
	cmd.Stderr = &stderr
	if err := cmd.Run(); err != nil {
		message := stderr.String()
		if message == "" {
			message = stdout.String()
		}
		if message == "" {
			message = "handler invocation failed"
		}
		return nil, fmt.Errorf("%s", message)
	}
	var response map[string]any
	if err := json.Unmarshal(stdout.Bytes(), &response); err != nil {
		return nil, fmt.Errorf("decode handler response: %w", err)
	}
	return response, nil
}
