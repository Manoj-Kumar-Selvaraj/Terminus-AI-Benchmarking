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

type Workshop struct {
	ID         string
	Attendee      string
	Amount     int
	Status     string
	WorkshopType string
	VisitDate  string
}

type Refund struct {
	WorkshopID     string
	Attendee      string
	Amount     int
	WorkshopType string
	RefundDate string
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
	workshopHeader, workshopRows, err := readCSV("/app/data/workshops.csv")
	if err != nil {
		return err
	}
	refundHeader, refundRows, err := readCSV("/app/data/refunds.csv")
	if err != nil {
		return err
	}
	dated := has(workshopHeader, "workshop_date") && has(refundHeader, "refund_date")
	workshops, err := loadWorkshops(workshopRows, dated)
	if err != nil {
		return err
	}
	refunds, err := loadRefunds(refundRows, dated)
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
	return writeOutputs(workshops, refunds, openDates, dated)
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

func loadWorkshops(rows [][]string, dated bool) ([]Workshop, error) {
	out := make([]Workshop, 0, len(rows))
	for _, row := range rows {
		amount, err := strconv.Atoi(clean(row[2]))
		if err != nil {
			return nil, err
		}
		workshop := Workshop{ID: clean(row[0]), Attendee: clean(row[1]), Amount: amount, Status: strings.ToUpper(clean(row[3])), WorkshopType: canonicalWorkshopType(row[4])}
		if dated && len(row) > 5 {
			workshop.VisitDate = clean(row[5])
		}
		out = append(out, workshop)
	}
	return out, nil
}

func loadRefunds(rows [][]string, dated bool) ([]Refund, error) {
	out := make([]Refund, 0, len(rows))
	for _, row := range rows {
		amount, err := strconv.Atoi(clean(row[2]))
		if err != nil {
			return nil, err
		}
		refund := Refund{WorkshopID: clean(row[0]), Attendee: clean(row[1]), Amount: amount, WorkshopType: canonicalWorkshopType(row[3])}
		if dated && len(row) > 4 {
			refund.RefundDate = clean(row[4])
		}
		out = append(out, refund)
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

func writeOutputs(workshops []Workshop, refunds []Refund, openDates map[string]bool, dated bool) error {
	if err := os.MkdirAll("/app/out", 0o755); err != nil {
		return err
	}
	reportPath := filepath.Join("/app/out", "workshop_refund_report.csv")
	reportFile, err := os.Create(reportPath)
	if err != nil {
		return err
	}
	defer reportFile.Close()
	writer := csv.NewWriter(reportFile)
	defer writer.Flush()
	if err := writer.Write([]string{"workshop_id", "attendee_id", "workshop_type", "amount_cents", "status"}); err != nil {
		return err
	}

	summary := Summary{}
	used := make([]bool, len(workshops))
	for _, refund := range refunds {
		matchIndex := findMatch(workshops, refund, used, openDates, dated)
		accessType := ""
		status := "UNMATCHED"
		if matchIndex >= 0 {
			used[matchIndex] = true
			accessType = workshops[matchIndex].WorkshopType
			status = "MATCHED"
			summary.MatchedCount++
			summary.MatchedAmountCents += refund.Amount
		} else {
			summary.UnmatchedCount++
			summary.UnmatchedAmountCents += refund.Amount
		}
		if err := writer.Write([]string{refund.WorkshopID, refund.Attendee, accessType, strconv.Itoa(refund.Amount), status}); err != nil {
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
	return os.WriteFile("/app/out/workshop_refund_summary.json", append(data, '\n'), 0o644)
}

func findMatch(workshops []Workshop, refund Refund, used []bool, openDates map[string]bool, dated bool) int {
	best := -1
	for i := range workshops {
		if used[i] {
			continue
		}
		workshop := workshops[i]
		if !eligible(workshop, refund, openDates, dated) {
			continue
		}
		if !dated {
			return i
		}
		if best < 0 || workshop.VisitDate > workshops[best].VisitDate || (workshop.VisitDate == workshops[best].VisitDate && i < best) {
			best = i
		}
	}
	return best
}

func eligible(workshop Workshop, refund Refund, openDates map[string]bool, dated bool) bool {
	if workshop.ID != refund.WorkshopID || workshop.Attendee != refund.Attendee || workshop.Amount != refund.Amount || workshop.Status != "ACTIVE" || !allowedWorkshopType(workshop.WorkshopType) || workshop.WorkshopType != refund.WorkshopType {
		return false
	}
	if dated {
		if refund.RefundDate == "" || workshop.VisitDate == "" || !openDates[refund.RefundDate] || refund.RefundDate > workshop.VisitDate {
			return false
		}
	}
	return true
}

func clean(value string) string {
	return strings.TrimSpace(value)
}

func canonicalWorkshopType(accessType string) string {
	switch strings.ToUpper(clean(accessType)) {
	case "BW":
		return "BREW"
	case "RS":
		return "ROAST"
	case "CP":
		return "CUP"
	default:
		return strings.ToUpper(clean(accessType))
	}
}

func allowedWorkshopType(accessType string) bool {
	accessType = canonicalWorkshopType(accessType)
	return accessType == "BREW" || accessType == "ROAST" || accessType == "CUP"
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
test -s /app/out/workshop_refund_report.csv
test -s /app/out/workshop_refund_summary.json