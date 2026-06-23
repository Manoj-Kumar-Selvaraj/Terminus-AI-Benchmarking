package main

import (
	"encoding/csv"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strconv"
)

type Fill struct {
	ID       string
	Member string
	Amount   int
	Status   string
	Reason   string
}

type Reversal struct {
	FillID string
	Member  string
	Amount    int
	Reason    string
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
	fills, err := loadFills("/app/data/fills.csv")
	if err != nil {
		return err
	}
	reversals, err := loadReversals("/app/data/reversals.csv")
	if err != nil {
		return err
	}
	return writeOutputs(fills, reversals)
}

func loadFills(path string) ([]Fill, error) {
	rows, err := readRows(path)
	if err != nil {
		return nil, err
	}
	out := make([]Fill, 0, len(rows))
	for _, row := range rows {
		amount, err := strconv.Atoi(row[2])
		if err != nil {
			return nil, err
		}
		out = append(out, Fill{ID: row[0], Member: row[1], Amount: amount, Status: row[3], Reason: row[4]})
	}
	return out, nil
}

func loadReversals(path string) ([]Reversal, error) {
	rows, err := readRows(path)
	if err != nil {
		return nil, err
	}
	out := make([]Reversal, 0, len(rows))
	for _, row := range rows {
		amount, err := strconv.Atoi(row[2])
		if err != nil {
			return nil, err
		}
		out = append(out, Reversal{FillID: row[0], Member: row[1], Amount: amount, Reason: row[3]})
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

func writeOutputs(fills []Fill, reversals []Reversal) error {
	if err := os.MkdirAll("/app/out", 0o755); err != nil {
		return err
	}
	reportPath := filepath.Join("/app/out", "reversal_report.csv")
	reportFile, err := os.Create(reportPath)
	if err != nil {
		return err
	}
	defer reportFile.Close()
	writer := csv.NewWriter(reportFile)
	defer writer.Flush()
	if err := writer.Write([]string{"fill_id", "member_id", "reason", "amount_cents", "status"}); err != nil {
		return err
	}

	summary := Summary{}
	for _, reversal := range reversals {
		match := findMatch(fills, reversal)
		reason := ""
		status := "UNMATCHED"
		if match != nil {
			reason = match.Reason
			status = "MATCHED"
			summary.MatchedCount++
			summary.MatchedAmountCents -= reversal.Amount
		} else {
			summary.UnmatchedCount++
			summary.UnmatchedAmountCents += reversal.Amount
		}
		if err := writer.Write([]string{
			reversal.FillID,
			reversal.Member,
			reason,
			strconv.Itoa(reversal.Amount),
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
	return os.WriteFile("/app/out/reversal_summary.json", append(summaryBytes, '\n'), 0o644)
}

func findMatch(fills []Fill, reversal Reversal) *Fill {
	for i := range fills {
		fill := &fills[i]
		if len(fill.ID) >= 8 && len(reversal.FillID) >= 8 &&
			fill.ID[:8] == reversal.FillID[:8] &&
			fill.Member == reversal.Member &&
			fill.Amount == reversal.Amount &&
			fill.Status == "POSTED" &&
			allowedReason(fill.Reason) &&
			fill.Reason == reversal.Reason {
			return fill
		}
	}
	return nil
}

func allowedReason(reason string) bool {
	return reason == "RX" || reason == "COB"
}
