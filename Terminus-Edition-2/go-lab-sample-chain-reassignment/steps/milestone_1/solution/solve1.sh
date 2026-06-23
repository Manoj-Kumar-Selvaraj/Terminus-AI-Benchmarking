#!/usr/bin/env bash
set -euo pipefail

cat > /app/cmd/reconcile/main.go <<'GO'
package main

import (
	"log"

	"golabsamplechainreassignment/internal/reconcile"
)

func main() {
	if err := reconcile.Run("/app"); err != nil {
		log.Fatal(err)
	}
}
GO

cat > /app/internal/reconcile/types.go <<'GO'
package reconcile

type Accession struct {
	SampleID string
	PatientID string
	ChainID string
	Kind string
	Amount string
	SourceTS string
	Status string
	Location string
	Consumed bool
	Index int
}

type Reassignment struct {
	ActionID string
	SampleID string
	PatientID string
	ChainID string
	Kind string
	Amount string
	ActionTS string
	Reason string
	Location string
}

type Window struct {
	ChainID string
	OpenTS string
	CloseTS string
	State string
}

type OutputRow struct {
	ActionID string
	SampleID string
	PatientID string
	ChainID string
	Kind string
	Amount string
	Reason string
	MatchedSourceTS string
	Status string
}
GO

cat > /app/internal/reconcile/io.go <<'GO'
package reconcile

import (
	"encoding/csv"
	"fmt"
	"os"
	"path/filepath"
	"strings"
)

func readMaps(path string) ([]map[string]string, error) {
	f, err := os.Open(path)
	if err != nil {
		return nil, err
	}
	defer f.Close()

	r := csv.NewReader(f)
	r.FieldsPerRecord = -1
	rows, err := r.ReadAll()
	if err != nil {
		return nil, err
	}
	if len(rows) == 0 {
		return nil, fmt.Errorf("%s has no header", path)
	}
	headers := rows[0]
	out := make([]map[string]string, 0, len(rows)-1)
	for _, row := range rows[1:] {
		m := map[string]string{}
		for i, key := range headers {
			value := ""
			if i < len(row) {
				value = row[i]
			}
			m[strings.TrimSpace(key)] = strings.TrimSpace(value)
		}
		out = append(out, m)
	}
	return out, nil
}

func loadAccessions(base string) ([]Accession, error) {
	rows, err := readMaps(filepath.Join(base, "data", "accessions.csv"))
	if err != nil {
		return nil, err
	}
	out := make([]Accession, 0, len(rows))
	for i, row := range rows {
		out = append(out, Accession{
			SampleID: row["sample_id"], PatientID: row["patient_id"], ChainID: row["chain_id"],
			Kind: row["kind"], Amount: row["amount"], SourceTS: row["source_ts"], Status: row["status"],
			Location: row["location"], Index: i,
		})
	}
	return out, nil
}

func loadReassignments(base string) ([]Reassignment, error) {
	rows, err := readMaps(filepath.Join(base, "data", "reassignments.csv"))
	if err != nil {
		return nil, err
	}
	out := make([]Reassignment, 0, len(rows))
	for _, row := range rows {
		out = append(out, Reassignment{
			ActionID: row["action_id"], SampleID: row["sample_id"], PatientID: row["patient_id"], ChainID: row["chain_id"],
			Kind: row["kind"], Amount: row["amount"], ActionTS: row["action_ts"], Reason: row["reason"], Location: row["location"],
		})
	}
	return out, nil
}

func writeReport(base string, rows []OutputRow, summary Summary) error {
	if err := os.MkdirAll(filepath.Join(base, "out"), 0o755); err != nil {
		return err
	}
	report, err := os.Create(filepath.Join(base, "out", "reassignment_report.csv"))
	if err != nil {
		return err
	}
	w := csv.NewWriter(report)
	if err := w.Write([]string{"action_id", "sample_id", "patient_id", "chain_id", "kind", "amount", "reason", "matched_source_ts", "status"}); err != nil {
		return err
	}
	for _, row := range rows {
		if err := w.Write([]string{row.ActionID, row.SampleID, row.PatientID, row.ChainID, row.Kind, row.Amount, row.Reason, row.MatchedSourceTS, row.Status}); err != nil {
			return err
		}
	}
	w.Flush()
	if err := w.Error(); err != nil {
		return err
	}
	if err := report.Close(); err != nil {
		return err
	}

	body := fmt.Sprintf("matched_count=%d\nmatched_amount=%d\nunmatched_count=%d\nunmatched_amount=%d\n", summary.MatchedCount, summary.MatchedAmount, summary.UnmatchedCount, summary.UnmatchedAmount)
	return os.WriteFile(filepath.Join(base, "out", "reassignment_summary.txt"), []byte(body), 0o644)
}
GO

cat > /app/internal/reconcile/config.go <<'GO'
package reconcile

import (
	"path/filepath"
	"strings"
)

func loadWindows(base string) ([]Window, error) {
	rows, err := readMaps(filepath.Join(base, "config", "windows.csv"))
	if err != nil {
		return nil, err
	}
	out := make([]Window, 0, len(rows))
	for _, row := range rows {
		out = append(out, Window{ChainID: row["chain_id"], OpenTS: row["open_ts"], CloseTS: row["close_ts"], State: row["state"]})
	}
	return out, nil
}

func loadAliases(base string) (map[string]string, error) {
	aliases := map[string]string{}
	if !featureAliases {
		return aliases, nil
	}
	rows, err := readMaps(filepath.Join(base, "config", "kind_aliases.csv"))
	if err != nil {
		return nil, err
	}
	for _, row := range rows {
		alias := upper(row["alias"])
		canonical := upper(row["canonical"])
		if alias == "" || !canonicalKind(canonical) {
			continue
		}
		if _, exists := aliases[alias]; !exists {
			aliases[alias] = canonical
		}
	}
	return aliases, nil
}

func loadReasons(base string) (map[string]bool, error) {
	reasons := map[string]bool{}
	if !featureReasonConfig {
		return reasons, nil
	}
	rows, err := readMaps(filepath.Join(base, "config", "reasons.csv"))
	if err != nil {
		return nil, err
	}
	for _, row := range rows {
		reason := upper(row["reason"])
		eligible := upper(row["eligible"])
		if reason != "" {
			reasons[reason] = eligible == "Y"
		}
	}
	return reasons, nil
}

func upper(s string) string {
	return strings.ToUpper(strings.TrimSpace(s))
}
GO

cat > /app/internal/reconcile/engine.go <<'GO'
package reconcile

import (
	"strconv"
	"time"
)

const (
	featureAliases = false
	featureWindows = false
	featureReasonConfig = false
)

type Summary struct {
	MatchedCount int
	MatchedAmount int
	UnmatchedCount int
	UnmatchedAmount int
}

func Run(base string) error {
	sources, err := loadAccessions(base)
	if err != nil {
		return err
	}
	actions, err := loadReassignments(base)
	if err != nil {
		return err
	}
	aliases, err := loadAliases(base)
	if err != nil {
		return err
	}
	reasons, err := loadReasons(base)
	if err != nil {
		return err
	}
	windows, err := loadWindows(base)
	if err != nil {
		return err
	}
	rows, summary := Reconcile(sources, actions, aliases, reasons, windows)
	return writeReport(base, rows, summary)
}

func Reconcile(sources []Accession, actions []Reassignment, aliases map[string]string, reasons map[string]bool, windows []Window) ([]OutputRow, Summary) {
	out := make([]OutputRow, 0, len(actions))
	summary := Summary{}
	for _, action := range actions {
		best := -1
		for i := range sources {
			if !eligible(sources[i], action, aliases, reasons, windows) {
				continue
			}
			if best < 0 || betterSource(sources[i], sources[best]) {
				best = i
			}
		}

		if best >= 0 {
			sources[best].Consumed = true
			amount, _ := parsePositiveAmount(action.Amount)
			summary.MatchedCount++
			summary.MatchedAmount += amount
			kind, _ := normalizeKind(sources[best].Kind, aliases)
			out = append(out, OutputRow{ActionID: action.ActionID, SampleID: action.SampleID, PatientID: action.PatientID, ChainID: action.ChainID, Kind: kind, Amount: action.Amount, Reason: action.Reason, MatchedSourceTS: sources[best].SourceTS, Status: "MATCHED"})
			continue
		}

		summary.UnmatchedCount++
		if amount, ok := parsePositiveAmount(action.Amount); ok {
			summary.UnmatchedAmount += amount
		}
		out = append(out, OutputRow{ActionID: action.ActionID, SampleID: action.SampleID, PatientID: action.PatientID, ChainID: action.ChainID, Amount: action.Amount, Reason: action.Reason, Status: "UNMATCHED"})
	}
	return out, summary
}

func eligible(source Accession, action Reassignment, aliases map[string]string, reasons map[string]bool, windows []Window) bool {
	if source.Consumed {
		return false
	}
	if source.SampleID != action.SampleID || source.PatientID != action.PatientID || source.ChainID != action.ChainID || source.Location != action.Location {
		return false
	}
	if source.Status != "RECEIVED" {
		return false
	}
	sourceAmount, sourceOK := parsePositiveAmount(source.Amount)
	actionAmount, actionOK := parsePositiveAmount(action.Amount)
	if !sourceOK || !actionOK || sourceAmount != actionAmount {
		return false
	}
	sourceTS, sourceTimeOK := parseTimestamp(source.SourceTS)
	actionTS, actionTimeOK := parseTimestamp(action.ActionTS)
	if !sourceTimeOK || !actionTimeOK || actionTS.Before(sourceTS) {
		return false
	}
	sourceKind, sourceKindOK := normalizeKind(source.Kind, aliases)
	actionKind, actionKindOK := normalizeKind(action.Kind, aliases)
	if !sourceKindOK || !actionKindOK || sourceKind != actionKind {
		return false
	}
	if !reasonEligible(action.Reason, reasons) {
		return false
	}
	if featureWindows && !withinWindow(source, action, windows) {
		return false
	}
	return true
}

func betterSource(candidate Accession, current Accession) bool {
	if featureWindows {
		if candidate.SourceTS > current.SourceTS {
			return true
		}
		if candidate.SourceTS == current.SourceTS && candidate.Index < current.Index {
			return true
		}
		return false
	}
	return candidate.Index < current.Index
}

func canonicalKind(kind string) bool {
	kind = upper(kind)
	if kind == "CHEM" || kind == "HEME" {
		return true
	}
	return featureAliases && kind == "MICRO"
}

func normalizeKind(raw string, aliases map[string]string) (string, bool) {
	kind := upper(raw)
	if featureAliases {
		if canonical, ok := aliases[kind]; ok {
			kind = canonical
		}
	}
	if !canonicalKind(kind) {
		return "", false
	}
	return kind, true
}

func reasonEligible(reason string, reasons map[string]bool) bool {
	if featureReasonConfig {
		return reasons[upper(reason)]
	}
	reason = upper(reason)
	return reason == "SPLIT" || reason == "REROUTE" || reason == "RECHECK"
}

func parsePositiveAmount(raw string) (int, bool) {
	if raw == "" {
		return 0, false
	}
	for _, r := range raw {
		if r < '0' || r > '9' {
			return 0, false
		}
	}
	amount, err := strconv.Atoi(raw)
	if err != nil || amount <= 0 {
		return 0, false
	}
	return amount, true
}

func parseTimestamp(raw string) (time.Time, bool) {
	if len(raw) != 14 {
		return time.Time{}, false
	}
	for _, r := range raw {
		if r < '0' || r > '9' {
			return time.Time{}, false
		}
	}
	parsed, err := time.Parse("20060102150405", raw)
	if err != nil {
		return time.Time{}, false
	}
	return parsed, true
}

func withinWindow(source Accession, action Reassignment, windows []Window) bool {
	sourceTS, sourceOK := parseTimestamp(source.SourceTS)
	actionTS, actionOK := parseTimestamp(action.ActionTS)
	if !sourceOK || !actionOK {
		return false
	}
	for _, window := range windows {
		if window.ChainID != source.ChainID || upper(window.State) != "OPEN" {
			continue
		}
		openTS, openOK := parseTimestamp(window.OpenTS)
		closeTS, closeOK := parseTimestamp(window.CloseTS)
		if !openOK || !closeOK {
			continue
		}
		if (sourceTS.Equal(openTS) || sourceTS.After(openTS)) && (sourceTS.Equal(closeTS) || sourceTS.Before(closeTS)) && (actionTS.Equal(sourceTS) || actionTS.After(sourceTS)) && (actionTS.Equal(closeTS) || actionTS.Before(closeTS)) {
			return true
		}
	}
	return false
}
GO

/app/scripts/run_batch.sh
