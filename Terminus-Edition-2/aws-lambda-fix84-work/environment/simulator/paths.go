package main

import (
	"os"
	"path/filepath"
)

func appRoot() string {
	if value := os.Getenv("APP_ROOT"); value != "" {
		return value
	}
	return "/app"
}

func configPath(name string) string {
	return filepath.Join(appRoot(), "config", name)
}

func dataPath(name string) string {
	return filepath.Join(appRoot(), "data", name)
}

func ledgerPath() string {
	if value := os.Getenv("SIDE_EFFECT_LEDGER"); value != "" {
		return value
	}
	return dataPath("side_effect_ledger.json")
}

func dlqPath() string {
	if value := os.Getenv("DLQ_STATE"); value != "" {
		return value
	}
	return dataPath("dlq_state.json")
}
