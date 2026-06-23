#!/usr/bin/env bash
set -euo pipefail
cd /app

if grep -q 'func loadPolicy' /app/cmd/reconcile/main.go && ! grep -q 'func clinicCalendarOK' /app/cmd/reconcile/main.go; then
  /app/scripts/run_batch.sh
  test -s /app/out/credit_report.csv
  test -s /app/out/credit_summary.json
  exit 0
fi

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

type Visit struct {
	ID          string
	Owner       string
	Amount      int
	Status      string
	Clinic      string
	ServiceDate string
	Row         int
}

type Credit struct {
	VisitID    string
	Owner      string
	Amount     int
	Clinic     string
	CreditDate string
}

type Policy struct {
	Enabled  bool
	Priority int
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
	visits, err := loadVisits("/app/data/visits.csv")
	if err != nil {
		return err
	}
	credits, err := loadCredits("/app/data/credits.csv")
	if err != nil {
		return err
	}
	openDates, err := loadOpenDates("/app/config/cutoff_calendar.txt")
	if err != nil {
		return err
	}
	policy, err := loadPolicy("/app/config/clinic_policy.csv")
	if err != nil {
		return err
	}
	return writeOutputs(visits, credits, openDates, policy)
}

func loadVisits(path string) ([]Visit, error) {
	rows, err := readRows(path)
	if err != nil {
		return nil, err
	}
	out := make([]Visit, 0, len(rows))
	for i, row := range rows {
		amount, err := strconv.Atoi(clean(row[2]))
		if err != nil {
			return nil, err
		}
		serviceDate := ""
		if len(row) > 5 {
			serviceDate = clean(row[5])
		}
		out = append(out, Visit{
			ID: clean(row[0]), Owner: clean(row[1]), Amount: amount,
			Status: strings.ToUpper(clean(row[3])), Clinic: canonicalClinic(row[4]),
			ServiceDate: serviceDate, Row: i,
		})
	}
	return out, nil
}

func loadCredits(path string) ([]Credit, error) {
	rows, err := readRows(path)
	if err != nil {
		return nil, err
	}
	out := make([]Credit, 0, len(rows))
	for _, row := range rows {
		amount, err := strconv.Atoi(clean(row[2]))
		if err != nil {
			return nil, err
		}
		creditDate := ""
		if len(row) > 4 {
			creditDate = clean(row[4])
		}
		out = append(out, Credit{
			VisitID: clean(row[0]), Owner: clean(row[1]), Amount: amount,
			Clinic: canonicalClinic(row[3]), CreditDate: creditDate,
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

func loadOpenDates(path string) (map[string]bool, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	openDates := map[string]bool{}
	for _, line := range strings.Split(string(data), "\n") {
		fields := strings.Fields(line)
		if len(fields) >= 2 {
			openDates[fields[0]] = strings.EqualFold(fields[1], "open")
		}
	}
	return openDates, nil
}

func loadPolicy(path string) (map[string]Policy, error) {
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
	policy := map[string]Policy{}
	for _, row := range rows[1:] {
		if len(row) < 3 {
			continue
		}
		priority, err := strconv.Atoi(clean(row[2]))
		if err != nil || priority <= 0 {
			priority = 9999
		}
		policy[canonicalClinic(row[0])] = Policy{
			Enabled: strings.EqualFold(clean(row[1]), "true"),
			Priority: priority,
		}
	}
	return policy, nil
}

func writeOutputs(visits []Visit, credits []Credit, openDates map[string]bool, policy map[string]Policy) error {
	if err := os.MkdirAll("/app/out", 0o755); err != nil {
		return err
	}
	reportPath := filepath.Join("/app/out", "credit_report.csv")
	reportFile, err := os.Create(reportPath)
	if err != nil {
		return err
	}
	defer reportFile.Close()
	writer := csv.NewWriter(reportFile)
	defer writer.Flush()
	if err := writer.Write([]string{"visit_id", "owner_id", "clinic", "amount_cents", "status"}); err != nil {
		return err
	}

	summary := Summary{}
	used := make([]bool, len(visits))
	for _, credit := range credits {
		matchIndex := findMatch(visits, credit, used, openDates, policy)
		clinic := ""
		status := "UNMATCHED"
		if matchIndex >= 0 {
			used[matchIndex] = true
			clinic = visits[matchIndex].Clinic
			status = "MATCHED"
			summary.MatchedCount++
			summary.MatchedAmountCents += credit.Amount
		} else {
			summary.UnmatchedCount++
			summary.UnmatchedAmountCents += credit.Amount
		}
		if err := writer.Write([]string{
			credit.VisitID,
			credit.Owner,
			clinic,
			strconv.Itoa(credit.Amount),
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
	return os.WriteFile("/app/out/credit_summary.json", append(summaryBytes, '\n'), 0o644)
}

func findMatch(visits []Visit, credit Credit, used []bool, openDates map[string]bool, policy map[string]Policy) int {
	best := -1
	for i := range visits {
		if used[i] {
			continue
		}
		visit := visits[i]
		if !baseEligible(visit, credit, openDates, policy) {
			continue
		}
		if credit.Clinic != "ANY" && visit.Clinic != credit.Clinic {
			continue
		}
		if best < 0 || betterVisit(visit, visits[best], credit, policy) {
			best = i
		}
	}
	return best
}

func baseEligible(visit Visit, credit Credit, openDates map[string]bool, policy map[string]Policy) bool {
	clinicPolicy, ok := policy[visit.Clinic]
	return ok &&
		clinicPolicy.Enabled &&
		openDates[credit.CreditDate] &&
		credit.CreditDate != "" &&
		visit.ServiceDate != "" &&
		credit.CreditDate <= visit.ServiceDate &&
		visit.ID == credit.VisitID &&
		visit.Owner == credit.Owner &&
		visit.Amount == credit.Amount &&
		visit.Status == "CLOSED"
}

func betterVisit(candidate Visit, current Visit, credit Credit, policy map[string]Policy) bool {
	if candidate.ServiceDate != current.ServiceDate {
		return candidate.ServiceDate > current.ServiceDate
	}
	if credit.Clinic == "ANY" {
		candPriority := policy[candidate.Clinic].Priority
		curPriority := policy[current.Clinic].Priority
		if candPriority != curPriority {
			return candPriority < curPriority
		}
	}
	return candidate.Row < current.Row
}

func clean(value string) string {
	return strings.TrimSpace(value)
}

func canonicalClinic(clinic string) string {
	switch strings.ToUpper(clean(clinic)) {
	case "MN":
		return "MAIN"
	case "VAN":
		return "MOBILE"
	case "URG":
		return "ER"
	default:
		return strings.ToUpper(clean(clinic))
	}
}
GO

/app/scripts/run_batch.sh
test -s /app/out/credit_report.csv
test -s /app/out/credit_summary.json
