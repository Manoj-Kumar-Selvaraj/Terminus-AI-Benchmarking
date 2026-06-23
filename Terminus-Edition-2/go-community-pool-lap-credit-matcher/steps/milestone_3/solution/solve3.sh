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

type Lap struct {
	ID         string
	Swimmer    string
	Amount     int
	Status     string
	LaneTier   string
	LapDate    string
	HasLapDate bool
	Used       bool
}

type Credit struct {
	LapID         string
	Swimmer       string
	Amount        int
	LaneTier      string
	CreditDate    string
	HasCreditDate bool
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
	laps, err := loadLaps("/app/data/laps.csv")
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
	return writeOutputs(laps, credits, openDates)
}

func loadLaps(path string) ([]Lap, error) {
	rows, err := readRows(path)
	if err != nil {
		return nil, err
	}
	laps := make([]Lap, 0, len(rows))
	for _, row := range rows {
		amount, err := strconv.Atoi(clean(row["amount_cents"]))
		if err != nil {
			return nil, err
		}
		lapDate, hasLapDate := row["lap_date"]
		laps = append(laps, Lap{
			ID:         clean(row["lap_id"]),
			Swimmer:    clean(row["swimmer_id"]),
			Amount:     amount,
			Status:     strings.ToUpper(clean(row["status"])),
			LaneTier:   canonicalLaneTier(row["lane_tier"]),
			LapDate:    clean(lapDate),
			HasLapDate: hasLapDate,
		})
	}
	return laps, nil
}

func loadCredits(path string) ([]Credit, error) {
	rows, err := readRows(path)
	if err != nil {
		return nil, err
	}
	credits := make([]Credit, 0, len(rows))
	for _, row := range rows {
		amount, err := strconv.Atoi(clean(row["amount_cents"]))
		if err != nil {
			return nil, err
		}
		creditDate, hasCreditDate := row["credit_date"]
		credits = append(credits, Credit{
			LapID:         clean(row["lap_id"]),
			Swimmer:       clean(row["swimmer_id"]),
			Amount:        amount,
			LaneTier:      canonicalLaneTier(row["lane_tier"]),
			CreditDate:    clean(creditDate),
			HasCreditDate: hasCreditDate,
		})
	}
	return credits, nil
}

func readRows(path string) ([]map[string]string, error) {
	f, err := os.Open(path)
	if err != nil {
		return nil, err
	}
	defer f.Close()
	reader := csv.NewReader(f)
	reader.FieldsPerRecord = -1
	data, err := reader.ReadAll()
	if err != nil {
		return nil, err
	}
	if len(data) == 0 {
		return nil, nil
	}
	header := data[0]
	rows := make([]map[string]string, 0, len(data)-1)
	for _, record := range data[1:] {
		row := map[string]string{}
		for i, name := range header {
			if i < len(record) {
				row[clean(name)] = record[i]
			} else {
				row[clean(name)] = ""
			}
		}
		rows = append(rows, row)
	}
	return rows, nil
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

func writeOutputs(laps []Lap, credits []Credit, openDates map[string]bool) error {
	if err := os.MkdirAll("/app/out", 0o755); err != nil {
		return err
	}
	reportFile, err := os.Create(filepath.Join("/app/out", "lap_credit_report.csv"))
	if err != nil {
		return err
	}
	defer reportFile.Close()
	writer := csv.NewWriter(reportFile)
	defer writer.Flush()
	if err := writer.Write([]string{"lap_id", "swimmer_id", "lane_tier", "amount_cents", "status"}); err != nil {
		return err
	}

	summary := Summary{}
	for _, credit := range credits {
		matchIndex := findMatch(laps, credit, openDates)
		status := "UNMATCHED"
		laneTier := ""
		if matchIndex >= 0 {
			laps[matchIndex].Used = true
			status = "MATCHED"
			laneTier = laps[matchIndex].LaneTier
			summary.MatchedCount++
			summary.MatchedAmountCents += credit.Amount
		} else {
			summary.UnmatchedCount++
			summary.UnmatchedAmountCents += credit.Amount
		}
		if err := writer.Write([]string{
			credit.LapID,
			credit.Swimmer,
			laneTier,
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
	return os.WriteFile("/app/out/lap_credit_summary.json", append(summaryBytes, '\n'), 0o644)
}

func findMatch(laps []Lap, credit Credit, openDates map[string]bool) int {
	best := -1
	for i := range laps {
		lap := &laps[i]
		if lap.Used ||
			lap.ID != credit.LapID ||
			lap.Swimmer != credit.Swimmer ||
			lap.Amount != credit.Amount ||
			lap.Status != "COMPLETED" ||
			!allowedLaneTier(lap.LaneTier) ||
			lap.LaneTier != credit.LaneTier {
			continue
		}

		datedSchema := lap.HasLapDate || credit.HasCreditDate
		if datedSchema {
			if lap.LapDate == "" ||
				credit.CreditDate == "" ||
				!openDates[credit.CreditDate] ||
				credit.CreditDate > lap.LapDate {
				continue
			}
		}

		if best < 0 ||
			lap.LapDate > laps[best].LapDate ||
			(lap.LapDate == laps[best].LapDate && i < best) {
			best = i
		}
	}
	return best
}

func canonicalLaneTier(value string) string {
	switch strings.ToUpper(clean(value)) {
	case "SL":
		return "SLOW"
	case "MD":
		return "MED"
	case "FS":
		return "FAST"
	default:
		return strings.ToUpper(clean(value))
	}
}

func allowedLaneTier(value string) bool {
	value = canonicalLaneTier(value)
	return value == "SLOW" || value == "MED" || value == "FAST"
}

func clean(value string) string {
	return strings.TrimSpace(value)
}
GO

/app/scripts/run_batch.sh
test -s /app/out/lap_credit_report.csv
test -s /app/out/lap_credit_summary.json
