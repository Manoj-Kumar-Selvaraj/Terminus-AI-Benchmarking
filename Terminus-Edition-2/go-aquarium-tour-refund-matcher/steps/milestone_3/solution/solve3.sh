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

type Tour struct {
	ID         string
	Guest      string
	Amount     int
	Status     string
	TourType string
	VisitDate  string
}

type Refund struct {
	TourID     string
	Guest      string
	Amount     int
	TourType string
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
	tourHeader, tourRows, err := readCSV("/app/data/tours.csv")
	if err != nil {
		return err
	}
	refundHeader, refundRows, err := readCSV("/app/data/refunds.csv")
	if err != nil {
		return err
	}
	dated := has(tourHeader, "tour_date") && has(refundHeader, "refund_date")
	tours, err := loadTours(tourRows, dated)
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
	return writeOutputs(tours, refunds, openDates, dated)
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

func loadTours(rows [][]string, dated bool) ([]Tour, error) {
	out := make([]Tour, 0, len(rows))
	for _, row := range rows {
		amount, err := strconv.Atoi(clean(row[2]))
		if err != nil {
			return nil, err
		}
		tour := Tour{ID: clean(row[0]), Guest: clean(row[1]), Amount: amount, Status: strings.ToUpper(clean(row[3])), TourType: canonicalTourType(row[4])}
		if dated && len(row) > 5 {
			tour.VisitDate = clean(row[5])
		}
		out = append(out, tour)
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
		refund := Refund{TourID: clean(row[0]), Guest: clean(row[1]), Amount: amount, TourType: canonicalTourType(row[3])}
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

func writeOutputs(tours []Tour, refunds []Refund, openDates map[string]bool, dated bool) error {
	if err := os.MkdirAll("/app/out", 0o755); err != nil {
		return err
	}
	reportPath := filepath.Join("/app/out", "tour_refund_report.csv")
	reportFile, err := os.Create(reportPath)
	if err != nil {
		return err
	}
	defer reportFile.Close()
	writer := csv.NewWriter(reportFile)
	defer writer.Flush()
	if err := writer.Write([]string{"tour_id", "guest_id", "tour_type", "amount_cents", "status"}); err != nil {
		return err
	}

	summary := Summary{}
	used := make([]bool, len(tours))
	for _, refund := range refunds {
		matchIndex := findMatch(tours, refund, used, openDates, dated)
		accessType := ""
		status := "UNMATCHED"
		if matchIndex >= 0 {
			used[matchIndex] = true
			accessType = tours[matchIndex].TourType
			status = "MATCHED"
			summary.MatchedCount++
			summary.MatchedAmountCents += refund.Amount
		} else {
			summary.UnmatchedCount++
			summary.UnmatchedAmountCents += refund.Amount
		}
		if err := writer.Write([]string{refund.TourID, refund.Guest, accessType, strconv.Itoa(refund.Amount), status}); err != nil {
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
	return os.WriteFile("/app/out/tour_refund_summary.json", append(data, '\n'), 0o644)
}

func findMatch(tours []Tour, refund Refund, used []bool, openDates map[string]bool, dated bool) int {
	best := -1
	for i := range tours {
		if used[i] {
			continue
		}
		tour := tours[i]
		if !eligible(tour, refund, openDates, dated) {
			continue
		}
		if !dated {
			return i
		}
		if best < 0 || tour.VisitDate > tours[best].VisitDate || (tour.VisitDate == tours[best].VisitDate && i < best) {
			best = i
		}
	}
	return best
}

func eligible(tour Tour, refund Refund, openDates map[string]bool, dated bool) bool {
	if tour.ID != refund.TourID || tour.Guest != refund.Guest || tour.Amount != refund.Amount || tour.Status != "ACTIVE" || !allowedTourType(tour.TourType) || tour.TourType != refund.TourType {
		return false
	}
	if dated {
		if refund.RefundDate == "" || tour.VisitDate == "" || !openDates[refund.RefundDate] || refund.RefundDate > tour.VisitDate {
			return false
		}
	}
	return true
}

func clean(value string) string {
	return strings.TrimSpace(value)
}

func canonicalTourType(accessType string) string {
	switch strings.ToUpper(clean(accessType)) {
	case "RF":
		return "REEF"
	case "SH":
		return "SHARK"
	case "VP":
		return "VIP"
	default:
		return strings.ToUpper(clean(accessType))
	}
}

func allowedTourType(accessType string) bool {
	accessType = canonicalTourType(accessType)
	return accessType == "REEF" || accessType == "SHARK" || accessType == "VIP"
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
test -s /app/out/tour_refund_report.csv
test -s /app/out/tour_refund_summary.json