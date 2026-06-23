package main

import (
	"encoding/csv"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strconv"
)

type Haul struct {
	ID       string
	Customer string
	Amount   int
	Status   string
	Route   string
}

type Adjustment struct {
	HaulID string
	Customer  string
	Amount    int
	Route    string
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
	hauls, err := loadHauls("/app/data/hauls.csv")
	if err != nil {
		return err
	}
	adjustments, err := loadAdjustments("/app/data/adjustments.csv")
	if err != nil {
		return err
	}
	return writeOutputs(hauls, adjustments)
}

func loadHauls(path string) ([]Haul, error) {
	rows, err := readRows(path)
	if err != nil {
		return nil, err
	}
	out := make([]Haul, 0, len(rows))
	for _, row := range rows {
		amount, err := strconv.Atoi(row[2])
		if err != nil {
			return nil, err
		}
		out = append(out, Haul{ID: row[0], Customer: row[1], Amount: amount, Status: row[3], Route: row[4]})
	}
	return out, nil
}

func loadAdjustments(path string) ([]Adjustment, error) {
	rows, err := readRows(path)
	if err != nil {
		return nil, err
	}
	out := make([]Adjustment, 0, len(rows))
	for _, row := range rows {
		amount, err := strconv.Atoi(row[2])
		if err != nil {
			return nil, err
		}
		out = append(out, Adjustment{HaulID: row[0], Customer: row[1], Amount: amount, Route: row[3]})
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

func writeOutputs(hauls []Haul, adjustments []Adjustment) error {
	if err := os.MkdirAll("/app/out", 0o755); err != nil {
		return err
	}
	reportPath := filepath.Join("/app/out", "adjustment_report.csv")
	reportFile, err := os.Create(reportPath)
	if err != nil {
		return err
	}
	defer reportFile.Close()
	writer := csv.NewWriter(reportFile)
	defer writer.Flush()
	if err := writer.Write([]string{"haul_id", "account_id", "route", "amount_cents", "status"}); err != nil {
		return err
	}

	summary := Summary{}
	for _, adjustment := range adjustments {
		match := findMatch(hauls, adjustment)
		route := ""
		status := "UNMATCHED"
		if match != nil {
			route = match.Route
			status = "MATCHED"
			summary.MatchedCount++
			summary.MatchedAmountCents -= adjustment.Amount
		} else {
			summary.UnmatchedCount++
			summary.UnmatchedAmountCents += adjustment.Amount
		}
		if err := writer.Write([]string{
			adjustment.HaulID,
			adjustment.Customer,
			route,
			strconv.Itoa(adjustment.Amount),
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
	return os.WriteFile("/app/out/adjustment_summary.json", append(summaryBytes, '\n'), 0o644)
}

func findMatch(hauls []Haul, adjustment Adjustment) *Haul {
	for i := range hauls {
		haul := &hauls[i]
		if len(haul.ID) >= 8 && len(adjustment.HaulID) >= 8 &&
			haul.ID[:8] == adjustment.HaulID[:8] &&
			haul.Customer == adjustment.Customer &&
			haul.Amount == adjustment.Amount &&
			haul.Status == "COMPLETED" &&
			allowedRoute(haul.Route) &&
			haul.Route == adjustment.Route {
			return haul
		}
	}
	return nil
}

func allowedRoute(route string) bool {
	return route == "RESI" || route == "COMM" || route == "IND"
}
