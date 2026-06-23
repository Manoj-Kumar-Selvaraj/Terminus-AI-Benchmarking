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
	Mode   string
}

type Rebate struct {
	TripID string
	Customer  string
	Amount    int
	Mode    string
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
	trips, err := loadTrips("/app/data/trips.csv")
	if err != nil {
		return err
	}
	rebates, err := loadRebates("/app/data/rebates.csv")
	if err != nil {
		return err
	}
	return writeOutputs(trips, rebates)
}

func loadTrips(path string) ([]Trip, error) {
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
		out = append(out, Trip{ID: row[0], Customer: row[1], Amount: amount, Status: row[3], Mode: row[4]})
	}
	return out, nil
}

func loadRebates(path string) ([]Rebate, error) {
	rows, err := readRows(path)
	if err != nil {
		return nil, err
	}
	out := make([]Rebate, 0, len(rows))
	for _, row := range rows {
		amount, err := strconv.Atoi(row[2])
		if err != nil {
			return nil, err
		}
		out = append(out, Rebate{TripID: row[0], Customer: row[1], Amount: amount, Mode: row[3]})
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

func writeOutputs(trips []Trip, rebates []Rebate) error {
	if err := os.MkdirAll("/app/out", 0o755); err != nil {
		return err
	}
	reportPath := filepath.Join("/app/out", "rebate_report.csv")
	reportFile, err := os.Create(reportPath)
	if err != nil {
		return err
	}
	defer reportFile.Close()
	writer := csv.NewWriter(reportFile)
	defer writer.Flush()
	if err := writer.Write([]string{"trip_id", "rider_id", "mode", "amount_cents", "status"}); err != nil {
		return err
	}

	summary := Summary{}
	for _, rebate := range rebates {
		match := findMatch(trips, rebate)
		mode := ""
		status := "UNMATCHED"
		if match != nil {
			mode = match.Mode
			status = "MATCHED"
			summary.MatchedCount++
			summary.MatchedAmountCents -= rebate.Amount
		} else {
			summary.UnmatchedCount++
			summary.UnmatchedAmountCents += rebate.Amount
		}
		if err := writer.Write([]string{
			rebate.TripID,
			rebate.Customer,
			mode,
			strconv.Itoa(rebate.Amount),
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
	return os.WriteFile("/app/out/rebate_summary.json", append(summaryBytes, '\n'), 0o644)
}

func findMatch(trips []Trip, rebate Rebate) *Trip {
	for i := range trips {
		trip := &trips[i]
		if len(trip.ID) >= 8 && len(rebate.TripID) >= 8 &&
			trip.ID[:8] == rebate.TripID[:8] &&
			trip.Customer == rebate.Customer &&
			trip.Amount == rebate.Amount &&
			trip.Status == "TAPPED" &&
			allowedMode(trip.Mode) &&
			trip.Mode == rebate.Mode {
			return trip
		}
	}
	return nil
}

func allowedMode(mode string) bool {
	return mode == "BUS" || mode == "RAIL" || mode == "FERRY"
}
