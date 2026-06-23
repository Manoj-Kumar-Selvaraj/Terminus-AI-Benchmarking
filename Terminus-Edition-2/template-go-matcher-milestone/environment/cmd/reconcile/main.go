package main

import (
	"encoding/csv"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strconv"
)

type Record struct {
	ID       string
	Account  string
	Amount   int
	Status   string
	Tier     string
}

type Adjustment struct {
	RecordID string
	Account  string
	Amount   int
	Tier     string
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
	records, err := loadRecords("/app/data/records.csv")
	if err != nil {
		return err
	}
	adjustments, err := loadAdjustments("/app/data/adjustments.csv")
	if err != nil {
		return err
	}
	return writeOutputs(records, adjustments)
}

func loadRecords(path string) ([]Record, error) {
	rows, err := readRows(path)
	if err != nil {
		return nil, err
	}
	out := make([]Record, 0, len(rows))
	for _, row := range rows {
		amount, err := strconv.Atoi(row[2])
		if err != nil {
			return nil, err
		}
		out = append(out, Record{ID: row[0], Account: row[1], Amount: amount, Status: row[3], Tier: row[4]})
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
		out = append(out, Adjustment{RecordID: row[0], Account: row[1], Amount: amount, Tier: row[3]})
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

func writeOutputs(records []Record, adjustments []Adjustment) error {
	if err := os.MkdirAll("/app/out", 0o755); err != nil {
		return err
	}
	reportPath := filepath.Join("/app/out", "wrong_report.csv")
	reportFile, err := os.Create(reportPath)
	if err != nil {
		return err
	}
	defer reportFile.Close()
	writer := csv.NewWriter(reportFile)
	defer writer.Flush()
	if err := writer.Write([]string{"record_id", "account_id", "tier", "amount_cents", "status"}); err != nil {
		return err
	}

	summary := Summary{}
	for _, adjustment := range adjustments {
		match := findMatch(records, adjustment)
		tier := ""
		status := "UNMATCHED"
		if match != nil {
			tier = match.Tier
			status = "MATCHED"
			summary.MatchedCount++
			summary.MatchedAmountCents -= adjustment.Amount
		} else {
			summary.UnmatchedCount++
			summary.UnmatchedAmountCents += adjustment.Amount
		}
		if err := writer.Write([]string{
			adjustment.RecordID,
			adjustment.Account,
			tier,
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
	return os.WriteFile("/app/out/wrong_summary.json", append(summaryBytes, '\n'), 0o644)
}

func findMatch(records []Record, adjustment Adjustment) *Record {
	for i := range records {
		record := &records[i]
		if len(record.ID) >= 8 && len(adjustment.RecordID) >= 8 &&
			record.ID[:8] == adjustment.RecordID[:8] &&
			record.Account == adjustment.Account &&
			record.Amount == adjustment.Amount &&
			record.Status == "ACTIVE" &&
			allowedTier(record.Tier) &&
			record.Tier == adjustment.Tier {
			return record
		}
	}
	return nil
}

func allowedTier(tier string) bool {
	return tier == "TIER_A"
}
