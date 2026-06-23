package main

import (
	"encoding/csv"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strconv"
)

type Pass struct {
	ID       string
	Customer string
	Amount   int
	Status   string
	AccessType   string
}

type Refund struct {
	PassID string
	Customer  string
	Amount    int
	AccessType    string
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
	passes, err := loadPasses("/app/data/passes.csv")
	if err != nil {
		return err
	}
	refunds, err := loadRefunds("/app/data/refunds.csv")
	if err != nil {
		return err
	}
	return writeOutputs(passes, refunds)
}

func loadPasses(path string) ([]Pass, error) {
	rows, err := readRows(path)
	if err != nil {
		return nil, err
	}
	out := make([]Pass, 0, len(rows))
	for _, row := range rows {
		amount, err := strconv.Atoi(row[2])
		if err != nil {
			return nil, err
		}
		out = append(out, Pass{ID: row[0], Customer: row[1], Amount: amount, Status: row[3], AccessType: row[4]})
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
		out = append(out, Refund{PassID: row[0], Customer: row[1], Amount: amount, AccessType: row[3]})
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

func writeOutputs(passes []Pass, refunds []Refund) error {
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
	if err := writer.Write([]string{"pass_id", "guest_id", "access_type", "amount_cents", "status"}); err != nil {
		return err
	}

	summary := Summary{}
	for _, refund := range refunds {
		match := findMatch(passes, refund)
		access_type := ""
		status := "UNMATCHED"
		if match != nil {
			access_type = match.AccessType
			status = "MATCHED"
			summary.MatchedCount++
			summary.MatchedAmountCents -= refund.Amount
		} else {
			summary.UnmatchedCount++
			summary.UnmatchedAmountCents += refund.Amount
		}
		if err := writer.Write([]string{
			refund.PassID,
			refund.Customer,
			access_type,
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

func findMatch(passes []Pass, refund Refund) *Pass {
	for i := range passes {
		pass := &passes[i]
		if len(pass.ID) >= 8 && len(refund.PassID) >= 8 &&
			pass.ID[:8] == refund.PassID[:8] &&
			pass.Customer == refund.Customer &&
			pass.Amount == refund.Amount &&
			pass.Status == "ACTIVE" &&
			allowedAccessType(pass.AccessType) &&
			pass.AccessType == refund.AccessType {
			return pass
		}
	}
	return nil
}

func allowedAccessType(access_type string) bool {
	return access_type == "DAY" || access_type == "SEASON" || access_type == "VIP"
}
