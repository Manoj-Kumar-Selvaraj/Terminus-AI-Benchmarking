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

type Booking struct {
	ID         string
	Dancer      string
	Amount     int
	Status     string
	RecitalType string
	VisitDate  string
}

type Credit struct {
	BookingID     string
	Dancer      string
	Amount     int
	RecitalType string
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
	bookingHeader, bookingRows, err := readCSV("/app/data/bookings.csv")
	if err != nil {
		return err
	}
	creditHeader, creditRows, err := readCSV("/app/data/credits.csv")
	if err != nil {
		return err
	}
	dated := has(bookingHeader, "recital_date") && has(creditHeader, "credit_date")
	bookings, err := loadBookings(bookingRows, dated)
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
	return writeOutputs(bookings, credits, openDates, dated)
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

func loadBookings(rows [][]string, dated bool) ([]Booking, error) {
	out := make([]Booking, 0, len(rows))
	for _, row := range rows {
		amount, err := strconv.Atoi(clean(row[2]))
		if err != nil {
			return nil, err
		}
		booking := Booking{ID: clean(row[0]), Dancer: clean(row[1]), Amount: amount, Status: strings.ToUpper(clean(row[3])), RecitalType: canonicalRecitalType(row[4])}
		if dated && len(row) > 5 {
			booking.VisitDate = clean(row[5])
		}
		out = append(out, booking)
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
		credit := Credit{BookingID: clean(row[0]), Dancer: clean(row[1]), Amount: amount, RecitalType: canonicalRecitalType(row[3])}
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

func writeOutputs(bookings []Booking, credits []Credit, openDates map[string]bool, dated bool) error {
	if err := os.MkdirAll("/app/out", 0o755); err != nil {
		return err
	}
	reportPath := filepath.Join("/app/out", "recital_credit_report.csv")
	reportFile, err := os.Create(reportPath)
	if err != nil {
		return err
	}
	defer reportFile.Close()
	writer := csv.NewWriter(reportFile)
	defer writer.Flush()
	if err := writer.Write([]string{"booking_id", "dancer_id", "recital_type", "amount_cents", "status"}); err != nil {
		return err
	}

	summary := Summary{}
	used := make([]bool, len(bookings))
	for _, credit := range credits {
		matchIndex := findMatch(bookings, credit, used, openDates, dated)
		accessType := ""
		status := "UNMATCHED"
		if matchIndex >= 0 {
			used[matchIndex] = true
			accessType = bookings[matchIndex].RecitalType
			status = "MATCHED"
			summary.MatchedCount++
			summary.MatchedAmountCents += credit.Amount
		} else {
			summary.UnmatchedCount++
			summary.UnmatchedAmountCents += credit.Amount
		}
		if err := writer.Write([]string{credit.BookingID, credit.Dancer, accessType, strconv.Itoa(credit.Amount), status}); err != nil {
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
	return os.WriteFile("/app/out/recital_credit_summary.json", append(data, '\n'), 0o644)
}

func findMatch(bookings []Booking, credit Credit, used []bool, openDates map[string]bool, dated bool) int {
	best := -1
	for i := range bookings {
		if used[i] {
			continue
		}
		booking := bookings[i]
		if !eligible(booking, credit, openDates, dated) {
			continue
		}
		if !dated {
			return i
		}
		if best < 0 || booking.VisitDate > bookings[best].VisitDate || (booking.VisitDate == bookings[best].VisitDate && i < best) {
			best = i
		}
	}
	return best
}

func eligible(booking Booking, credit Credit, openDates map[string]bool, dated bool) bool {
	if booking.ID != credit.BookingID || booking.Dancer != credit.Dancer || booking.Amount != credit.Amount || booking.Status != "ACTIVE" || !allowedRecitalType(booking.RecitalType) || booking.RecitalType != credit.RecitalType {
		return false
	}
	if dated {
		if credit.CreditDate == "" || booking.VisitDate == "" || !openDates[credit.CreditDate] || credit.CreditDate > booking.VisitDate {
			return false
		}
	}
	return true
}

func clean(value string) string {
	return strings.TrimSpace(value)
}

func canonicalRecitalType(accessType string) string {
	switch strings.ToUpper(clean(accessType)) {
	case "SL":
		return "SOLO"
	case "GP":
		return "GROUP"
	case "ST":
		return "STAGE"
	default:
		return strings.ToUpper(clean(accessType))
	}
}

func allowedRecitalType(accessType string) bool {
	accessType = canonicalRecitalType(accessType)
	return accessType == "SOLO" || accessType == "GROUP" || accessType == "STAGE"
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
test -s /app/out/recital_credit_report.csv
test -s /app/out/recital_credit_summary.json