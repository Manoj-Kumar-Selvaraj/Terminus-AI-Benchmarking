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

type Rental struct {
	ID         string
	Account      string
	Amount     int
	Status     string
	EquipmentType string
	VisitDate  string
}

type Credit struct {
	RentalID     string
	Account      string
	Amount     int
	EquipmentType string
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
	rentalHeader, rentalRows, err := readCSV("/app/data/rentals.csv")
	if err != nil {
		return err
	}
	creditHeader, creditRows, err := readCSV("/app/data/credits.csv")
	if err != nil {
		return err
	}
	dated := has(rentalHeader, "rental_date") && has(creditHeader, "credit_date")
	rentals, err := loadRentals(rentalRows, dated)
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
	return writeOutputs(rentals, credits, openDates, dated)
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

func loadRentals(rows [][]string, dated bool) ([]Rental, error) {
	out := make([]Rental, 0, len(rows))
	for _, row := range rows {
		amount, err := strconv.Atoi(clean(row[2]))
		if err != nil {
			return nil, err
		}
		rental := Rental{ID: clean(row[0]), Account: clean(row[1]), Amount: amount, Status: strings.ToUpper(clean(row[3])), EquipmentType: canonicalEquipmentType(row[4])}
		if dated && len(row) > 5 {
			rental.VisitDate = clean(row[5])
		}
		out = append(out, rental)
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
		credit := Credit{RentalID: clean(row[0]), Account: clean(row[1]), Amount: amount, EquipmentType: canonicalEquipmentType(row[3])}
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

func writeOutputs(rentals []Rental, credits []Credit, openDates map[string]bool, dated bool) error {
	if err := os.MkdirAll("/app/out", 0o755); err != nil {
		return err
	}
	reportPath := filepath.Join("/app/out", "rental_credit_report.csv")
	reportFile, err := os.Create(reportPath)
	if err != nil {
		return err
	}
	defer reportFile.Close()
	writer := csv.NewWriter(reportFile)
	defer writer.Flush()
	if err := writer.Write([]string{"rental_id", "account_id", "equipment_type", "amount_cents", "status"}); err != nil {
		return err
	}

	summary := Summary{}
	used := make([]bool, len(rentals))
	for _, credit := range credits {
		matchIndex := findMatch(rentals, credit, used, openDates, dated)
		accessType := ""
		status := "UNMATCHED"
		if matchIndex >= 0 {
			used[matchIndex] = true
			accessType = rentals[matchIndex].EquipmentType
			status = "MATCHED"
			summary.MatchedCount++
			summary.MatchedAmountCents += credit.Amount
		} else {
			summary.UnmatchedCount++
			summary.UnmatchedAmountCents += credit.Amount
		}
		if err := writer.Write([]string{credit.RentalID, credit.Account, accessType, strconv.Itoa(credit.Amount), status}); err != nil {
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
	return os.WriteFile("/app/out/rental_credit_summary.json", append(data, '\n'), 0o644)
}

func findMatch(rentals []Rental, credit Credit, used []bool, openDates map[string]bool, dated bool) int {
	best := -1
	for i := range rentals {
		if used[i] {
			continue
		}
		rental := rentals[i]
		if !eligible(rental, credit, openDates, dated) {
			continue
		}
		if !dated {
			return i
		}
		if best < 0 || rental.VisitDate > rentals[best].VisitDate || (rental.VisitDate == rentals[best].VisitDate && i < best) {
			best = i
		}
	}
	return best
}

func eligible(rental Rental, credit Credit, openDates map[string]bool, dated bool) bool {
	if rental.ID != credit.RentalID || rental.Account != credit.Account || rental.Amount != credit.Amount || rental.Status != "ACTIVE" || !allowedEquipmentType(rental.EquipmentType) || rental.EquipmentType != credit.EquipmentType {
		return false
	}
	if dated {
		if credit.CreditDate == "" || rental.VisitDate == "" || !openDates[credit.CreditDate] || credit.CreditDate > rental.VisitDate {
			return false
		}
	}
	return true
}

func clean(value string) string {
	return strings.TrimSpace(value)
}

func canonicalEquipmentType(accessType string) string {
	switch strings.ToUpper(clean(accessType)) {
	case "TR":
		return "TRACTOR"
	case "SP":
		return "SPRAY"
	case "LF":
		return "LIFT"
	default:
		return strings.ToUpper(clean(accessType))
	}
}

func allowedEquipmentType(accessType string) bool {
	accessType = canonicalEquipmentType(accessType)
	return accessType == "TRACTOR" || accessType == "SPRAY" || accessType == "LIFT"
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
test -s /app/out/rental_credit_report.csv
test -s /app/out/rental_credit_summary.json