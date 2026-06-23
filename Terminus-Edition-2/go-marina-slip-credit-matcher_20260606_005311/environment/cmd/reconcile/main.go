package main

import (
	"encoding/csv"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strconv"
)

type Slip struct {
	ID       string
	Customer string
	Amount   int
	Status   string
	DockZone   string
}

type Credit struct {
	SlipID string
	Customer  string
	Amount    int
	DockZone    string
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
	slips, err := loadSlips("/app/data/slips.csv")
	if err != nil {
		return err
	}
	credits, err := loadCredits("/app/data/credits.csv")
	if err != nil {
		return err
	}
	return writeOutputs(slips, credits)
}

func loadSlips(path string) ([]Slip, error) {
	rows, err := readRows(path)
	if err != nil {
		return nil, err
	}
	out := make([]Slip, 0, len(rows))
	for _, row := range rows {
		amount, err := strconv.Atoi(row[2])
		if err != nil {
			return nil, err
		}
		out = append(out, Slip{ID: row[0], Customer: row[1], Amount: amount, Status: row[3], DockZone: row[4]})
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
		out = append(out, Credit{SlipID: row[0], Customer: row[1], Amount: amount, DockZone: row[3]})
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

func writeOutputs(slips []Slip, credits []Credit) error {
	if err := os.MkdirAll("/app/out", 0o755); err != nil {
		return err
	}
	reportPath := filepath.Join("/app/out", "credit_report.csv")
	reportFile, err := os.Create(reportPath)
	if err != nil {
		return err
	}
	defer reportFile.Close()
	writer := csv.NewWriter(reportFile)
	defer writer.Flush()
	if err := writer.Write([]string{"slip_id", "member_id", "dock_zone", "amount_cents", "status"}); err != nil {
		return err
	}

	summary := Summary{}
	for _, credit := range credits {
		match := findMatch(slips, credit)
		dock_zone := ""
		status := "UNMATCHED"
		if match != nil {
			dock_zone = match.DockZone
			status = "MATCHED"
			summary.MatchedCount++
			summary.MatchedAmountCents -= credit.Amount
		} else {
			summary.UnmatchedCount++
			summary.UnmatchedAmountCents += credit.Amount
		}
		if err := writer.Write([]string{
			credit.SlipID,
			credit.Customer,
			dock_zone,
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
	return os.WriteFile("/app/out/credit_summary.json", append(summaryBytes, '\n'), 0o644)
}

func findMatch(slips []Slip, credit Credit) *Slip {
	for i := range slips {
		slip := &slips[i]
		if len(slip.ID) >= 8 && len(credit.SlipID) >= 8 &&
			slip.ID[:8] == credit.SlipID[:8] &&
			slip.Customer == credit.Customer &&
			slip.Amount == credit.Amount &&
			slip.Status == "DOCKED" &&
			allowedDockZone(slip.DockZone) &&
			slip.DockZone == credit.DockZone {
			return slip
		}
	}
	return nil
}

func allowedDockZone(dock_zone string) bool {
	return dock_zone == "NORTH" || dock_zone == "SOUTH" || dock_zone == "EAST"
}
