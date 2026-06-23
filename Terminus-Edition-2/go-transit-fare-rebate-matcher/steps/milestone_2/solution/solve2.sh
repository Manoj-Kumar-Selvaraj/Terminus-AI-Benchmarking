#!/usr/bin/env bash
set -euo pipefail

cat > /app/cmd/reconcile/main.go <<'GO'
package main

import (
	"encoding/csv"
	"encoding/json"
	"os"
	"strconv"
	"strings"
)

type Trip struct {
	ID       string
	Rider    string
	Route    string
	Amount   int
	Status   string
	Mode     string
}

type Rebate struct {
	TripID string
	Rider  string
	Route  string
	Amount int
	Mode   string
}

type Summary struct {
	MatchedCount         int `json:"matched_count"`
	MatchedAmountCents   int `json:"matched_amount_cents"`
	UnmatchedCount       int `json:"unmatched_count"`
	UnmatchedAmountCents int `json:"unmatched_amount_cents"`
}

func main() {
	if err := run(); err != nil {
		panic(err)
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
	records, err := readCSV(path)
	if err != nil {
		return nil, err
	}
	trips := []Trip{}
	for _, row := range records {
		amount, err := strconv.Atoi(clean(row["amount_cents"]))
		if err != nil {
			continue
		}
		trips = append(trips, Trip{
			ID:     clean(row["trip_id"]),
			Rider:  clean(row["rider_id"]),
			Route:  clean(row["route_id"]),
			Amount: amount,
			Status: strings.ToUpper(clean(row["status"])),
			Mode:   canonicalMode(row["mode"]),
		})
	}
	return trips, nil
}

func loadRebates(path string) ([]Rebate, error) {
	records, err := readCSV(path)
	if err != nil {
		return nil, err
	}
	rebates := []Rebate{}
	for _, row := range records {
		amount, err := strconv.Atoi(clean(row["amount_cents"]))
		if err != nil {
			continue
		}
		rebates = append(rebates, Rebate{
			TripID: clean(row["trip_id"]),
			Rider:  clean(row["rider_id"]),
			Route:  clean(row["route_id"]),
			Amount: amount,
			Mode:   canonicalMode(row["mode"]),
		})
	}
	return rebates, nil
}

func readCSV(path string) ([]map[string]string, error) {
	file, err := os.Open(path)
	if err != nil {
		return nil, err
	}
	defer file.Close()
	reader := csv.NewReader(file)
	reader.FieldsPerRecord = -1
	rows, err := reader.ReadAll()
	if err != nil {
		return nil, err
	}
	if len(rows) == 0 {
		return nil, nil
	}
	headers := rows[0]
	out := make([]map[string]string, 0, len(rows)-1)
	for _, values := range rows[1:] {
		row := map[string]string{}
		for i, header := range headers {
			value := ""
			if i < len(values) {
				value = values[i]
			}
			row[clean(header)] = value
		}
		out = append(out, row)
	}
	return out, nil
}

func writeOutputs(trips []Trip, rebates []Rebate) error {
	if err := os.MkdirAll("/app/out", 0o755); err != nil {
		return err
	}
	report, err := os.Create("/app/out/rebate_report.csv")
	if err != nil {
		return err
	}
	defer report.Close()
	writer := csv.NewWriter(report)
	defer writer.Flush()
	if err := writer.Write([]string{"trip_id", "rider_id", "mode", "amount_cents", "status"}); err != nil {
		return err
	}

	used := make([]bool, len(trips))
	summary := Summary{}
	for _, rebate := range rebates {
		match := findMatch(trips, rebate, used)
		if match >= 0 {
			used[match] = true
			summary.MatchedCount++
			summary.MatchedAmountCents += rebate.Amount
			if err := writer.Write([]string{rebate.TripID, rebate.Rider, trips[match].Mode, strconv.Itoa(rebate.Amount), "MATCHED"}); err != nil {
				return err
			}
		} else {
			summary.UnmatchedCount++
			summary.UnmatchedAmountCents += rebate.Amount
			if err := writer.Write([]string{rebate.TripID, rebate.Rider, "", strconv.Itoa(rebate.Amount), "UNMATCHED"}); err != nil {
				return err
			}
		}
	}
	writer.Flush()
	if err := writer.Error(); err != nil {
		return err
	}
	data, err := json.Marshal(summary)
	if err != nil {
		return err
	}
	return os.WriteFile("/app/out/rebate_summary.json", data, 0o644)
}

func findMatch(trips []Trip, rebate Rebate, used []bool) int {
	for i := range trips {
		trip := trips[i]
		if used[i] {
			continue
		}
		if trip.ID == rebate.TripID &&
			trip.Rider == rebate.Rider &&
			trip.Route == rebate.Route &&
			trip.Amount == rebate.Amount &&
			trip.Status == "TAPPED" &&
			allowedMode(trip.Mode) &&
			trip.Mode == rebate.Mode {
			return i
		}
	}
	return -1
}

func clean(value string) string {
	return strings.TrimSpace(value)
}

func canonicalMode(mode string) string {
	switch strings.ToUpper(clean(mode)) {
	case "BST":
		return "BUS"
	case "LRT":
		return "RAIL"
	case "FRY":
		return "FERRY"
	default:
		return strings.ToUpper(clean(mode))
	}
}

func allowedMode(mode string) bool {
	mode = canonicalMode(mode)
	return mode == "BUS" || mode == "RAIL" || mode == "FERRY"
}
GO

/app/scripts/run_batch.sh
test -s /app/out/rebate_report.csv
test -s /app/out/rebate_summary.json
