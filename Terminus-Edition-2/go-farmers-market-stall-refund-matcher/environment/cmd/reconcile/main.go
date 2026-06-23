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

type Stall struct {
	ID        string
	Customer  string
	Amount    int
	Status    string
	StallType string
}

type Refund struct {
	StallID   string
	Customer  string
	Amount    int
	StallType string
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
	stalls, err := loadStalles("/app/data/stalls.csv")
	if err != nil {
		return err
	}
	refunds, err := loadRefunds("/app/data/refunds.csv")
	if err != nil {
		return err
	}
	return writeOutputs(stalls, refunds)
}

func loadStalles(path string) ([]Stall, error) {
	rows, err := readRows(path)
	if err != nil {
		return nil, err
	}
	out := make([]Stall, 0, len(rows))
	for _, row := range rows {
		amount, err := strconv.Atoi(row[2])
		if err != nil {
			return nil, err
		}
		out = append(out, Stall{ID: row[0], Customer: row[1], Amount: amount, Status: row[3], StallType: row[4]})
	}
	return out, nil
}

func loadRefunds(path string) ([]Refund, error) {
	rows, err := readRows(path)
	if err != nil {
		return nil, err
	}
	out := make([]Refund, 0, len(rows))
	for _, row := range rows {
		amount, err := strconv.Atoi(row[2])
		if err != nil {
			return nil, err
		}
		out = append(out, Refund{StallID: row[0], Customer: row[1], Amount: amount, StallType: row[3]})
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

func writeOutputs(stalls []Stall, refunds []Refund) error {
	if err := os.MkdirAll("/app/out", 0o755); err != nil {
		return err
	}
	reportPath := filepath.Join("/app/out", "refund_report.csv")
	reportFile, err := os.Create(reportPath)
	if err != nil {
		return err
	}
	defer reportFile.Close()
	writer := csv.NewWriter(reportFile)
	defer writer.Flush()
	if err := writer.Write([]string{"stall_id", "vendor_id", "stall_type", "amount_cents", "status"}); err != nil {
		return err
	}

	summary := Summary{}
	for _, refund := range refunds {
		match := findMatch(stalls, refund)
		stallType := ""
		status := "UNMATCHED"
		if match != nil {
			stallType = match.StallType
			status = "MATCHED"
			summary.MatchedCount++
			summary.MatchedAmountCents -= refund.Amount
		} else {
			summary.UnmatchedCount++
			summary.UnmatchedAmountCents += refund.Amount
		}
		if err := writer.Write([]string{
			refund.StallID,
			refund.Customer,
			stallType,
			strconv.Itoa(refund.Amount),
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
	return os.WriteFile("/app/out/refund_summary.json", append(summaryBytes, '\n'), 0o644)
}

func findMatch(stalls []Stall, refund Refund) *Stall {
	for i := range stalls {
		stall := &stalls[i]
		if len(stall.ID) >= 8 && len(refund.StallID) >= 8 &&
			stall.ID[:8] == refund.StallID[:8] &&
			stall.Customer == refund.Customer &&
			stall.Amount == refund.Amount &&
			stall.Status == "RESERVED" &&
			allowedStallType(stall.StallType) &&
			stall.StallType == refund.StallType {
			return stall
		}
	}
	return nil
}

func allowedStallType(stallType string) bool {
	stallType = strings.ToUpper(strings.TrimSpace(stallType))
	return stallType == "PRODUCE" || stallType == "CRAFT"
}
