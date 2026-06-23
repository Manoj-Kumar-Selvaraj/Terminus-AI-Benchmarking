#!/usr/bin/env bash
set -euo pipefail

cat > /app/cmd/reconcile/main.go <<'GOEOF'
package main

import (
	"bufio"
	"encoding/csv"
	"encoding/json"
	"fmt"
	"os"
	"strconv"
	"strings"
)

const (
	passesPath   = "/app/data/passes.csv"
	creditsPath  = "/app/data/credits.csv"
	reportPath   = "/app/out/credit_report.csv"
	summaryPath  = "/app/out/credit_summary.json"
	calendarPath = "/app/config/cutoff_calendar.txt"
	methodsPath  = "/app/config/methods.csv"
)

type Pass struct {
	ID         string
	Customer   string
	Amount     int
	Status     string
	Program    string
	ValidUntil string
}

type Credit struct {
	PassID     string
	Customer   string
	Amount     int
	Program    string
	CreditDate string
}

type ProgramEntry struct {
	Enabled  bool
	Priority int
}

type Summary struct {
	MatchedCount         int `json:"matched_count"`
	MatchedAmountCents   int `json:"matched_amount_cents"`
	UnmatchedCount       int `json:"unmatched_count"`
	UnmatchedAmountCents int `json:"unmatched_amount_cents"`
}

func clean(v string) string { return strings.TrimSpace(v) }

func canonicalProgram(v string) string {
	switch strings.ToUpper(clean(v)) {
	case "GEN":
		return "GENERAL"
	case "TR":
		return "TOUR"
	case "MEM":
		return "MEMBER"
	default:
		return strings.ToUpper(clean(v))
	}
}

func loadPolicy() map[string]ProgramEntry {
	defaults := []string{"GENERAL", "TOUR", "MEMBER"}
	fallback := func() map[string]ProgramEntry {
		p := map[string]ProgramEntry{}
		for i, prog := range defaults {
			p[prog] = ProgramEntry{Enabled: true, Priority: i + 1}
		}
		return p
	}
	f, err := os.Open(methodsPath)
	if err != nil {
		return fallback()
	}
	defer f.Close()
	r := csv.NewReader(f)
	r.FieldsPerRecord = -1
	rows, err := r.ReadAll()
	if err != nil || len(rows) <= 1 {
		return fallback()
	}
	policy := map[string]ProgramEntry{}
	for idx, row := range rows[1:] {
		if len(row) < 2 {
			continue
		}
		prog := canonicalProgram(row[0])
		if prog == "" {
			continue
		}
		enabled := strings.EqualFold(clean(row[1]), "true")
		priority := 10000 + idx
		if len(row) >= 3 {
			if p, e := strconv.Atoi(clean(row[2])); e == nil {
				priority = p
			}
		}
		policy[prog] = ProgramEntry{Enabled: enabled, Priority: priority}
	}
	if len(policy) == 0 {
		return fallback()
	}
	return policy
}

func enabledProgram(prog string, policy map[string]ProgramEntry) bool {
	e, ok := policy[prog]
	return ok && e.Enabled
}

func programPriority(prog string, policy map[string]ProgramEntry) int {
	if e, ok := policy[prog]; ok {
		return e.Priority
	}
	return 99999
}

func loadOpenDates() (map[string]bool, error) {
	f, err := os.Open(calendarPath)
	if err != nil {
		return map[string]bool{}, nil
	}
	defer f.Close()
	dates := map[string]bool{}
	sc := bufio.NewScanner(f)
	for sc.Scan() {
		fields := strings.Fields(sc.Text())
		if len(fields) >= 2 && strings.EqualFold(fields[1], "open") {
			dates[fields[0]] = true
		}
	}
	return dates, sc.Err()
}

func readCSV(path string) ([][]string, error) {
	f, err := os.Open(path)
	if err != nil {
		return nil, err
	}
	defer f.Close()
	r := csv.NewReader(f)
	r.FieldsPerRecord = -1
	return r.ReadAll()
}

func dateMode(passRows, creditRows [][]string) bool {
	check := func(rows [][]string, col string) bool {
		if len(rows) == 0 {
			return false
		}
		for _, h := range rows[0] {
			if strings.EqualFold(clean(h), col) {
				return true
			}
		}
		return false
	}
	return check(passRows, "valid_until") || check(creditRows, "credit_date")
}

func loadPasses(rows [][]string, dated bool) ([]Pass, error) {
	out := make([]Pass, 0)
	for _, row := range rows[1:] {
		if len(row) < 5 {
			continue
		}
		amount, err := strconv.Atoi(clean(row[2]))
		if err != nil {
			return nil, err
		}
		validUntil := ""
		if dated && len(row) > 5 {
			validUntil = clean(row[5])
		}
		out = append(out, Pass{
			ID:         clean(row[0]),
			Customer:   clean(row[1]),
			Amount:     amount,
			Status:     strings.ToUpper(clean(row[3])),
			Program:    canonicalProgram(row[4]),
			ValidUntil: validUntil,
		})
	}
	return out, nil
}

func loadCredits(rows [][]string, dated bool) ([]Credit, error) {
	out := make([]Credit, 0)
	for _, row := range rows[1:] {
		if len(row) < 4 {
			continue
		}
		amount, err := strconv.Atoi(clean(row[2]))
		if err != nil {
			return nil, err
		}
		creditDate := ""
		if dated && len(row) > 4 {
			creditDate = clean(row[4])
		}
		out = append(out, Credit{
			PassID:     clean(row[0]),
			Customer:   clean(row[1]),
			Amount:     amount,
			Program:    canonicalProgram(row[3]),
			CreditDate: creditDate,
		})
	}
	return out, nil
}

func reportProgram(credit Credit, pass Pass) string {
	if credit.Program == "ANY" || credit.Program == "" {
		return pass.Program
	}
	return credit.Program
}

func betterCandidate(pass, best Pass, idx, bestIdx int, policy map[string]ProgramEntry) bool {
	if pass.ValidUntil != best.ValidUntil {
		return pass.ValidUntil > best.ValidUntil
	}
	p1 := programPriority(pass.Program, policy)
	p2 := programPriority(best.Program, policy)
	if p1 != p2 {
		return p1 < p2
	}
	return idx < bestIdx
}

func betterCandidateBlank(pass, best Pass, idx, bestIdx int, dated bool) bool {
	if dated && pass.ValidUntil != best.ValidUntil {
		return pass.ValidUntil > best.ValidUntil
	}
	return idx < bestIdx
}

func findMatch(passes []Pass, credit Credit, used []bool, openDates map[string]bool, dated bool, policy map[string]ProgramEntry) int {
	bestIndex := -1
	for i, pass := range passes {
		if used[i] {
			continue
		}
		if pass.ID != credit.PassID {
			continue
		}
		if pass.Customer != credit.Customer {
			continue
		}
		if pass.Amount != credit.Amount {
			continue
		}
		if pass.Status != "ACTIVE" {
			continue
		}
		if !enabledProgram(pass.Program, policy) {
			continue
		}
		if credit.Program != "ANY" && credit.Program != "" {
			if !enabledProgram(credit.Program, policy) {
				continue
			}
			if pass.Program != credit.Program {
				continue
			}
		}
		if dated {
			if pass.ValidUntil == "" && credit.CreditDate == "" {
				// undated backward compatibility when date columns exist but values are blank
			} else {
				if pass.ValidUntil == "" || credit.CreditDate == "" {
					continue
				}
				if !openDates[credit.CreditDate] {
					continue
				}
				if credit.CreditDate > pass.ValidUntil {
					continue
				}
			}
		}
		if bestIndex < 0 {
			bestIndex = i
		} else if credit.Program == "ANY" {
			if betterCandidate(pass, passes[bestIndex], i, bestIndex, policy) {
				bestIndex = i
			}
		} else if credit.Program == "" {
			if betterCandidateBlank(pass, passes[bestIndex], i, bestIndex, dated) {
				bestIndex = i
			}
		} else if dated {
			if betterCandidate(pass, passes[bestIndex], i, bestIndex, policy) {
				bestIndex = i
			}
		}
	}
	return bestIndex
}

func main() {
	if err := run(); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}

func run() error {
	passRows, err := readCSV(passesPath)
	if err != nil {
		return err
	}
	creditRows, err := readCSV(creditsPath)
	if err != nil {
		return err
	}
	dated := dateMode(passRows, creditRows)
	passes, err := loadPasses(passRows, dated)
	if err != nil {
		return err
	}
	credits, err := loadCredits(creditRows, dated)
	if err != nil {
		return err
	}
	policy := loadPolicy()
	openDates, err := loadOpenDates()
	if err != nil {
		return err
	}
	used := make([]bool, len(passes))
	if err := os.MkdirAll("/app/out", 0o755); err != nil {
		return err
	}
	f, err := os.Create(reportPath)
	if err != nil {
		return err
	}
	defer f.Close()
	w := csv.NewWriter(f)
	defer w.Flush()
	if err := w.Write([]string{"pass_id", "guest_id", "program", "amount_cents", "status"}); err != nil {
		return err
	}
	summary := Summary{}
	for _, credit := range credits {
		idx := findMatch(passes, credit, used, openDates, dated, policy)
		if idx >= 0 {
			used[idx] = true
			summary.MatchedCount++
			summary.MatchedAmountCents += credit.Amount
			if err := w.Write([]string{
				credit.PassID,
				credit.Customer,
				reportProgram(credit, passes[idx]),
				strconv.Itoa(credit.Amount),
				"MATCHED",
			}); err != nil {
				return err
			}
		} else {
			summary.UnmatchedCount++
			summary.UnmatchedAmountCents += credit.Amount
			if err := w.Write([]string{
				credit.PassID,
				credit.Customer,
				"",
				strconv.Itoa(credit.Amount),
				"UNMATCHED",
			}); err != nil {
				return err
			}
		}
	}
	if w.Error() != nil {
		return w.Error()
	}
	b, err := json.MarshalIndent(summary, "", "  ")
	if err != nil {
		return err
	}
	return os.WriteFile(summaryPath, append(b, '\n'), 0o644)
}
GOEOF

/app/scripts/run_batch.sh
test -s /app/out/credit_report.csv
test -s /app/out/credit_summary.json
