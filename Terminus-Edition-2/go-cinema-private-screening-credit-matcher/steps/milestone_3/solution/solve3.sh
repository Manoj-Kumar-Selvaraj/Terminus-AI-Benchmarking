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

type Screening struct {
	ID         string
	Host      string
	Amount     int
	Status     string
	ScreenType string
	VisitDate  string
}

type Credit struct {
	ScreeningID     string
	Host      string
	Amount     int
	ScreenType string
	CreditDate string
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
	screeningHeader, screeningRows, err := readCSV("/app/data/screenings.csv")
	if err != nil {
		return err
	}
	creditHeader, creditRows, err := readCSV("/app/data/credits.csv")
	if err != nil {
		return err
	}
	dated := has(screeningHeader, "screening_date") && has(creditHeader, "credit_date")
	screenings, err := loadScreenings(screeningRows, dated)
	if err != nil {
		return err
	}
	credits, err := loadCredits(creditRows, dated)
	if err != nil {
		return err
	}
	openDates := map[string]bool{}
	if dated {
		openDates, err = loadOpenDates("/app/config/cutoff_calendar.txt")
		if err != nil {
			return err
		}
	}
	return writeOutputs(screenings, credits, openDates, dated)
}

func readCSV(path string) ([]string, [][]string, error) {
	f, err := os.Open(path)
	if err != nil {
		return nil, nil, err
	}
	defer f.Close()
	reader := csv.NewReader(f)
	reader.FieldsPerRecord = -1
	rows, err := reader.ReadAll()
	if err != nil {
		return nil, nil, err
	}
	if len(rows) == 0 {
		return nil, nil, nil
	}
	return rows[0], rows[1:], nil
}

func loadScreenings(rows [][]string, dated bool) ([]Screening, error) {
	out := make([]Screening, 0, len(rows))
	for _, row := range rows {
		amount, err := strconv.Atoi(clean(row[2]))
		if err != nil {
			return nil, err
		}
		screening := Screening{ID: clean(row[0]), Host: clean(row[1]), Amount: amount, Status: strings.ToUpper(clean(row[3])), ScreenType: canonicalScreenType(row[4])}
		if dated && len(row) > 5 {
			screening.VisitDate = clean(row[5])
		}
		out = append(out, screening)
	}
	return out, nil
}

func loadCredits(rows [][]string, dated bool) ([]Credit, error) {
	out := make([]Credit, 0, len(rows))
	for _, row := range rows {
		amount, err := strconv.Atoi(clean(row[2]))
		if err != nil {
			return nil, err
		}
		credit := Credit{ScreeningID: clean(row[0]), Host: clean(row[1]), Amount: amount, ScreenType: canonicalScreenType(row[3])}
		if dated && len(row) > 4 {
			credit.CreditDate = clean(row[4])
		}
		out = append(out, credit)
	}
	return out, nil
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

func writeOutputs(screenings []Screening, credits []Credit, openDates map[string]bool, dated bool) error {
	if err := os.MkdirAll("/app/out", 0o755); err != nil {
		return err
	}
	reportPath := filepath.Join("/app/out", "screening_credit_report.csv")
	reportFile, err := os.Create(reportPath)
	if err != nil {
		return err
	}
	defer reportFile.Close()
	writer := csv.NewWriter(reportFile)
	defer writer.Flush()
	if err := writer.Write([]string{"screening_id", "host_id", "screen_type", "amount_cents", "status"}); err != nil {
		return err
	}

	summary := Summary{}
	used := make([]bool, len(screenings))
	for _, credit := range credits {
		matchIndex := findMatch(screenings, credit, used, openDates, dated)
		accessType := ""
		status := "UNMATCHED"
		if matchIndex >= 0 {
			used[matchIndex] = true
			accessType = screenings[matchIndex].ScreenType
			status = "MATCHED"
			summary.MatchedCount++
			summary.MatchedAmountCents += credit.Amount
		} else {
			summary.UnmatchedCount++
			summary.UnmatchedAmountCents += credit.Amount
		}
		if err := writer.Write([]string{credit.ScreeningID, credit.Host, accessType, strconv.Itoa(credit.Amount), status}); err != nil {
			return err
		}
	}
	if writer.Error() != nil {
		return writer.Error()
	}
	data, err := json.MarshalIndent(summary, "", "  ")
	if err != nil {
		return err
	}
	return os.WriteFile("/app/out/screening_credit_summary.json", append(data, '\n'), 0o644)
}

func findMatch(screenings []Screening, credit Credit, used []bool, openDates map[string]bool, dated bool) int {
	best := -1
	for i := range screenings {
		if used[i] {
			continue
		}
		screening := screenings[i]
		if !eligible(screening, credit, openDates, dated) {
			continue
		}
		if !dated {
			return i
		}
		if best < 0 || screening.VisitDate > screenings[best].VisitDate || (screening.VisitDate == screenings[best].VisitDate && i < best) {
			best = i
		}
	}
	return best
}

func eligible(screening Screening, credit Credit, openDates map[string]bool, dated bool) bool {
	if screening.ID != credit.ScreeningID || screening.Host != credit.Host || screening.Amount != credit.Amount || screening.Status != "ACTIVE" || !allowedScreenType(screening.ScreenType) || screening.ScreenType != credit.ScreenType {
		return false
	}
	if dated {
		if credit.CreditDate == "" || screening.VisitDate == "" || !openDates[credit.CreditDate] || credit.CreditDate > screening.VisitDate {
			return false
		}
	}
	return true
}

func clean(value string) string {
	return strings.TrimSpace(value)
}

func canonicalScreenType(accessType string) string {
	switch strings.ToUpper(clean(accessType)) {
	case "SM":
		return "SMALL"
	case "PM":
		return "PREM"
	case "IX":
		return "IMAX"
	default:
		return strings.ToUpper(clean(accessType))
	}
}

func allowedScreenType(accessType string) bool {
	accessType = canonicalScreenType(accessType)
	return accessType == "SMALL" || accessType == "PREM" || accessType == "IMAX"
}

func has(headers []string, name string) bool {
	for _, header := range headers {
		if strings.EqualFold(clean(header), name) {
			return true
		}
	}
	return false
}
GO

/app/scripts/run_batch.sh
test -s /app/out/screening_credit_report.csv
test -s /app/out/screening_credit_summary.json