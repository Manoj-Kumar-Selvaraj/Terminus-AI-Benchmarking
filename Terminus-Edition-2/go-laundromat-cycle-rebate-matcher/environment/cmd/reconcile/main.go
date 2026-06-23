package main

import (
	"encoding/csv"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strconv"
)

type Trip struct {
	ID       string
	Customer string
	Amount   int
	Status   string
	PassType   string
}

type Credit struct {
	TripID string
	Customer  string
	Amount    int
	PassType    string
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
	trips, err := loadCyclees("/app/data/cycles.csv")
	if err != nil {
		return err
	}
	credits, err := loadCredits("/app/data/rebates.csv")
	if err != nil {
		return err
	}
	return writeOutputs(trips, credits)
}

func loadCyclees(path string) ([]Trip, error) {
	rows, err := readRows(path)
	if err != nil {
		return nil, err
	}
	out := make([]Trip, 0, len(rows))
	for _, row := range rows {
		amount, err := strconv.Atoi(row[2])
		if err != nil {
			return nil, err
		}
		out = append(out, Trip{ID: row[0], Customer: row[1], Amount: amount, Status: row[3], PassType: row[4]})
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
		amount, err := strconv.Atoi(row[2])
		if err != nil {
			return nil, err
		}
		out = append(out, Credit{TripID: row[0], Customer: row[1], Amount: amount, PassType: row[3]})
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

func writeOutputs(trips []Trip, credits []Credit) error {
	if err := os.MkdirAll("/app/out", 0o755); err != nil {
		return err
	}
	reportPath := filepath.Join("/app/out", "cycle_rebate_report.csv")
	reportFile, err := os.Create(reportPath)
	if err != nil {
		return err
	}
	defer reportFile.Close()
	writer := csv.NewWriter(reportFile)
	defer writer.Flush()
	if err := writer.Write([]string{"cycle_id", "customer_id", "machine_tier", "amount_cents", "status"}); err != nil {
		return err
	}

	summary := Summary{}
	for _, credit := range credits {
		match := findMatch(trips, credit)
		pass_type := ""
		status := "UNMATCHED"
		if match != nil {
			pass_type = match.PassType
			status = "MATCHED"
			summary.MatchedCount++
			summary.MatchedAmountCents -= credit.Amount
		} else {
			summary.UnmatchedCount++
			summary.UnmatchedAmountCents += credit.Amount
		}
		if err := writer.Write([]string{
			credit.TripID,
			credit.Customer,
			pass_type,
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
	return os.WriteFile("/app/out/cycle_rebate_summary.json", append(summaryBytes, '\n'), 0o644)
}

func findMatch(trips []Trip, credit Credit) *Trip {
	for i := range trips {
		trip := &trips[i]
		if len(trip.ID) >= 8 && len(credit.TripID) >= 8 &&
			trip.ID[:8] == credit.TripID[:8] &&
			trip.Customer == credit.Customer &&
			trip.Amount == credit.Amount &&
			trip.Status == "COMPLETED" &&
			allowedPassType(trip.PassType) &&
			trip.PassType == credit.PassType {
			return trip
		}
	}
	return nil
}

func allowedPassType(pass_type string) bool {
	return pass_type == "WASH" || pass_type == "DRY" || pass_type == "COMBO"
}
