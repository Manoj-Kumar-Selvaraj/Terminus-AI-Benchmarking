package main

import (
	"encoding/csv"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strconv"
)

type Bill struct {
	ID       string
	Customer string
	Amount   int
	Status   string
	Channel   string
}

type Refund struct {
	BillID string
	Customer  string
	Amount    int
	Channel    string
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
	bills, err := loadBills("/app/data/bills.csv")
	if err != nil {
		return err
	}
	refunds, err := loadRefunds("/app/data/refunds.csv")
	if err != nil {
		return err
	}
	return writeOutputs(bills, refunds)
}

func loadBills(path string) ([]Bill, error) {
	rows, err := readRows(path)
	if err != nil {
		return nil, err
	}
	out := make([]Bill, 0, len(rows))
	for _, row := range rows {
		amount, err := strconv.Atoi(row[2])
		if err != nil {
			return nil, err
		}
		out = append(out, Bill{ID: row[0], Customer: row[1], Amount: amount, Status: row[3], Channel: row[4]})
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
		out = append(out, Refund{BillID: row[0], Customer: row[1], Amount: amount, Channel: row[3]})
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

func writeOutputs(bills []Bill, refunds []Refund) error {
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
	if err := writer.Write([]string{"bill_id", "customer_id", "channel", "amount_cents", "status"}); err != nil {
		return err
	}

	summary := Summary{}
	for _, refund := range refunds {
		match := findMatch(bills, refund)
		channel := ""
		status := "UNMATCHED"
		if match != nil {
			channel = match.Channel
			status = "MATCHED"
			summary.MatchedCount++
			summary.MatchedAmountCents -= refund.Amount
		} else {
			summary.UnmatchedCount++
			summary.UnmatchedAmountCents += refund.Amount
		}
		if err := writer.Write([]string{
			refund.BillID,
			refund.Customer,
			channel,
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

func findMatch(bills []Bill, refund Refund) *Bill {
	for i := range bills {
		bill := &bills[i]
		if len(bill.ID) >= 8 && len(refund.BillID) >= 8 &&
			bill.ID[:8] == refund.BillID[:8] &&
			bill.Customer == refund.Customer &&
			bill.Amount == refund.Amount &&
			bill.Status == "POSTED" &&
			allowedChannel(bill.Channel) &&
			bill.Channel == refund.Channel {
			return bill
		}
	}
	return nil
}

func allowedChannel(channel string) bool {
	return channel == "ACH" || channel == "WIRE"
}
