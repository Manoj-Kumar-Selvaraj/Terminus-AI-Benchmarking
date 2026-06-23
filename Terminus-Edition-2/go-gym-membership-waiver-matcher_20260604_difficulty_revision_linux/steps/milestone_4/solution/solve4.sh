#!/usr/bin/env bash
set -euo pipefail

cd /app

cat > /app/cmd/reconcile/main.go <<'GO'
package main

import (
	"encoding/csv"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strconv"
	"strings"
)

type Membership struct {
	ID          string
	Customer    string
	Amount      int
	Status      string
	Plan        string
	RenewalDate string
}

type Waiver struct {
	MembershipID string
	Customer     string
	Amount       int
	Plan         string
	WaiverDate   string
	Method       string
	HasMethod    bool
}

type Summary struct {
	MatchedCount         int `json:"matched_count"`
	MatchedAmountCents   int `json:"matched_amount_cents"`
	UnmatchedCount       int `json:"unmatched_count"`
	UnmatchedAmountCents int `json:"unmatched_amount_cents"`
}

func main() {
	if err := run(); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}

func run() error {
	memberships, err := loadMemberships("/app/data/memberships.csv")
	if err != nil {
		return err
	}
	waivers, err := loadWaivers("/app/data/waivers.csv")
	if err != nil {
		return err
	}
	openDates, err := loadOpenDates("/app/config/cutoff_calendar.txt")
	if err != nil {
		return err
	}
	enabledMethods, err := loadEnabledMethods("/app/config/methods.csv")
	if err != nil {
		return err
	}
	return writeOutputs(memberships, waivers, openDates, enabledMethods)
}

func loadMemberships(path string) ([]Membership, error) {
	rows, err := readRows(path)
	if err != nil {
		return nil, err
	}
	out := make([]Membership, 0, len(rows))
	for _, row := range rows {
		if len(row) < 5 {
			continue
		}
		amount, err := strconv.Atoi(clean(row[2]))
		if err != nil {
			return nil, err
		}
		renewalDate := ""
		if len(row) > 5 {
			renewalDate = clean(row[5])
		}
		out = append(out, Membership{
			ID: clean(row[0]), Customer: clean(row[1]), Amount: amount,
			Status: strings.ToUpper(clean(row[3])), Plan: canonicalPlan(row[4]), RenewalDate: renewalDate,
		})
	}
	return out, nil
}

func loadWaivers(path string) ([]Waiver, error) {
	rows, err := readRows(path)
	if err != nil {
		return nil, err
	}
	out := make([]Waiver, 0, len(rows))
	for _, row := range rows {
		if len(row) < 4 {
			continue
		}
		amount, err := strconv.Atoi(clean(row[2]))
		if err != nil {
			return nil, err
		}
		waiverDate := ""
		if len(row) > 4 {
			waiverDate = clean(row[4])
		}
		method := ""
		hasMethod := len(row) > 5
		if hasMethod {
			method = strings.ToUpper(clean(row[5]))
		}
		out = append(out, Waiver{
			MembershipID: clean(row[0]), Customer: clean(row[1]), Amount: amount,
			Plan: canonicalPlan(row[3]), WaiverDate: waiverDate, Method: method, HasMethod: hasMethod,
		})
	}
	return out, nil
}

func readRows(path string) ([][]string, error) {
	f, err := os.Open(path)
	if err != nil {
		return nil, err
	}
	defer f.Close()
	reader := csv.NewReader(f)
	reader.FieldsPerRecord = -1
	rows, err := reader.ReadAll()
	if err != nil {
		return nil, err
	}
	if len(rows) == 0 {
		return nil, nil
	}
	return rows[1:], nil
}

func writeOutputs(memberships []Membership, waivers []Waiver, openDates map[string]bool, enabledMethods map[string]bool) error {
	if err := os.MkdirAll("/app/out", 0o755); err != nil {
		return err
	}
	reportPath := filepath.Join("/app/out", "waiver_report.csv")
	reportFile, err := os.Create(reportPath)
	if err != nil {
		return err
	}
	defer reportFile.Close()
	writer := csv.NewWriter(reportFile)
	defer writer.Flush()
	if err := writer.Write([]string{"membership_id", "member_id", "plan", "amount_cents", "status"}); err != nil {
		return err
	}

	summary := Summary{}
	usedMemberships := make([]bool, len(memberships))
	for _, waiver := range waivers {
		matchIndex := findMatch(memberships, waiver, usedMemberships, openDates, enabledMethods)
		plan := ""
		status := "UNMATCHED"
		if matchIndex >= 0 {
			match := memberships[matchIndex]
			usedMemberships[matchIndex] = true
			plan = match.Plan
			status = "MATCHED"
			summary.MatchedCount++
			summary.MatchedAmountCents += waiver.Amount
		} else {
			summary.UnmatchedCount++
			summary.UnmatchedAmountCents += waiver.Amount
		}
		if err := writer.Write([]string{
			waiver.MembershipID,
			waiver.Customer,
			plan,
			strconv.Itoa(waiver.Amount),
			status,
		}); err != nil {
			return err
		}
	}
	if writer.Error() != nil {
		return writer.Error()
	}

	summaryBytes, err := json.MarshalIndent(summary, "", "  ")
	if err != nil {
		return err
	}
	return os.WriteFile("/app/out/waiver_summary.json", append(summaryBytes, '\n'), 0o644)
}

func findMatch(memberships []Membership, waiver Waiver, used []bool, openDates map[string]bool, enabledMethods map[string]bool) int {
	bestIndex := -1
	for i := range memberships {
		if used[i] {
			continue
		}
		membership := &memberships[i]
		if !eligibleMethod(waiver, enabledMethods) ||
			!openDates[waiver.WaiverDate] ||
			waiver.WaiverDate == "" ||
			membership.RenewalDate == "" ||
			waiver.WaiverDate > membership.RenewalDate ||
			membership.ID != waiver.MembershipID ||
			membership.Customer != waiver.Customer ||
			membership.Amount != waiver.Amount ||
			membership.Status != "ACTIVE" ||
			!allowedPlan(membership.Plan) ||
			membership.Plan != waiver.Plan {
			continue
		}
		if bestIndex < 0 || membership.RenewalDate > memberships[bestIndex].RenewalDate {
			bestIndex = i
		}
	}
	return bestIndex
}

func eligibleMethod(waiver Waiver, enabledMethods map[string]bool) bool {
	if !waiver.HasMethod {
		return true
	}
	return waiver.Method != "" && enabledMethods[waiver.Method]
}

func loadOpenDates(path string) (map[string]bool, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	openDates := map[string]bool{}
	for _, line := range strings.Split(string(data), "\n") {
		fields := strings.Fields(line)
		if len(fields) >= 2 && strings.EqualFold(fields[1], "open") {
			openDates[fields[0]] = true
		}
	}
	return openDates, nil
}

func loadEnabledMethods(path string) (map[string]bool, error) {
	f, err := os.Open(path)
	if err != nil {
		return nil, err
	}
	defer f.Close()
	reader := csv.NewReader(f)
	reader.FieldsPerRecord = -1
	rows, err := reader.ReadAll()
	if err != nil {
		return nil, err
	}
	enabled := map[string]bool{}
	for _, row := range rows[1:] {
		if len(row) < 2 {
			continue
		}
		method := strings.ToUpper(clean(row[0]))
		if method == "" {
			continue
		}
		if strings.EqualFold(clean(row[1]), "true") {
			enabled[method] = true
		}
	}
	return enabled, nil
}

func clean(value string) string {
	return strings.TrimSpace(value)
}

func canonicalPlan(plan string) string {
	switch strings.ToUpper(clean(plan)) {
	case "BAS":
		return "BASIC"
	case "PLU":
		return "PLUS"
	case "ELI":
		return "ELITE"
	default:
		return strings.ToUpper(clean(plan))
	}
}

func allowedPlan(plan string) bool {
	plan = canonicalPlan(plan)
	return plan == "BASIC" || plan == "PLUS" || plan == "ELITE"
}
GO

/app/scripts/run_batch.sh
test -s /app/out/waiver_report.csv
test -s /app/out/waiver_summary.json
