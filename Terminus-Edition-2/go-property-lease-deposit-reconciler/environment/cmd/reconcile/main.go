package main

import (
	"encoding/csv"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strconv"
)

type Lease struct {
	ID       string
	Customer string
	Amount   int
	Status   string
	Channel   string
}

type Deposit struct {
	LeaseID string
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
	leases, err := loadLeases("/app/data/leases.csv")
	if err != nil {
		return err
	}
	deposits, err := loadDeposits("/app/data/deposits.csv")
	if err != nil {
		return err
	}
	return writeOutputs(leases, deposits)
}

func loadLeases(path string) ([]Lease, error) {
	rows, err := readRows(path)
	if err != nil {
		return nil, err
	}
	out := make([]Lease, 0, len(rows))
	for _, row := range rows {
		amount, err := strconv.Atoi(row[2])
		if err != nil {
			return nil, err
		}
		out = append(out, Lease{ID: row[0], Customer: row[1], Amount: amount, Status: row[3], Channel: row[4]})
	}
	return out, nil
}

func loadDeposits(path string) ([]Deposit, error) {
	rows, err := readRows(path)
	if err != nil {
		return nil, err
	}
	out := make([]Deposit, 0, len(rows))
	for _, row := range rows {
		amount, err := strconv.Atoi(row[2])
		if err != nil {
			return nil, err
		}
		out = append(out, Deposit{LeaseID: row[0], Customer: row[1], Amount: amount, Channel: row[3]})
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

func writeOutputs(leases []Lease, deposits []Deposit) error {
	if err := os.MkdirAll("/app/out", 0o755); err != nil {
		return err
	}
	reportPath := filepath.Join("/app/out", "deposit_report.csv")
	reportFile, err := os.Create(reportPath)
	if err != nil {
		return err
	}
	defer reportFile.Close()
	writer := csv.NewWriter(reportFile)
	defer writer.Flush()
	if err := writer.Write([]string{"lease_id", "customer_id", "channel", "amount_cents", "status"}); err != nil {
		return err
	}

	summary := Summary{}
	for _, deposit := range deposits {
		match := findMatch(leases, deposit)
		channel := ""
		status := "UNMATCHED"
		if match != nil {
			channel = match.Channel
			status = "MATCHED"
			summary.MatchedCount++
			summary.MatchedAmountCents -= deposit.Amount
		} else {
			summary.UnmatchedCount++
			summary.UnmatchedAmountCents += deposit.Amount
		}
		if err := writer.Write([]string{
			deposit.LeaseID,
			deposit.Customer,
			channel,
			strconv.Itoa(deposit.Amount),
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
	return os.WriteFile("/app/out/deposit_summary.json", append(summaryBytes, '\n'), 0o644)
}

func findMatch(leases []Lease, deposit Deposit) *Lease {
	for i := range leases {
		lease := &leases[i]
		if len(lease.ID) >= 8 && len(deposit.LeaseID) >= 8 &&
			lease.ID[:8] == deposit.LeaseID[:8] &&
			lease.Customer == deposit.Customer &&
			lease.Amount == deposit.Amount &&
			lease.Status == "POSTED" &&
			allowedChannel(lease.Channel) &&
			lease.Channel == deposit.Channel {
			return lease
		}
	}
	return nil
}

func allowedChannel(channel string) bool {
	return channel == "ACH" || channel == "WIRE"
}
