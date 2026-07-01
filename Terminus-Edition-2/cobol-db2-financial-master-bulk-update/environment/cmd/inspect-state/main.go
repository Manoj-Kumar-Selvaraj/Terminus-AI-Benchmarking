package main

import (
	"encoding/json"
	"fmt"
	"os"

	"finbulk/internal/db2sim"
)

func main() {
	path := "/app/state/financial_master.json"
	if len(os.Args) > 1 {
		path = os.Args[1]
	}
	db, err := db2sim.Load(path)
	if err != nil {
		fmt.Fprintf(os.Stderr, "inspect-state: %v\n", err)
		os.Exit(1)
	}
	out := map[string]any{
		"master_count": len(asMap(db["master"])),
		"risk_count":   len(asMap(db["risk"])),
		"ledger_count": len(asSlice(db["ledger"])),
		"audit_count":  len(asSlice(db["audit"])),
		"reject_count": len(asSlice(db["rejects"])),
		"checkpoint":   db["checkpoint"],
	}
	enc := json.NewEncoder(os.Stdout)
	enc.SetIndent("", "  ")
	enc.SetEscapeHTML(false)
	if err := enc.Encode(out); err != nil {
		fmt.Fprintf(os.Stderr, "inspect-state: %v\n", err)
		os.Exit(1)
	}
}

func asMap(v any) map[string]any {
	m, _ := v.(map[string]any)
	if m == nil {
		return map[string]any{}
	}
	return m
}

func asSlice(v any) []any {
	s, _ := v.([]any)
	if s == nil {
		return []any{}
	}
	return s
}
