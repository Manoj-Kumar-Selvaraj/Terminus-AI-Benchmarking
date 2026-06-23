package main

import (
	"encoding/csv"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strconv"
)

type Account struct {
	ID       string
	Customer string
	Amount   int
	Status   string
	Channel   string
}

type Reimbursement struct {
	AccountID string
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
	accounts, err := loadAccounts("/app/data/accounts.csv")
	if err != nil {
		return err
	}
	reimbursements, err := loadReimbursements("/app/data/reimbursements.csv")
	if err != nil {
		return err
	}
	return writeOutputs(accounts, reimbursements)
}

func loadAccounts(path string) ([]Account, error) {
	rows, err := readRows(path)
	if err != nil {
		return nil, err
	}
	out := make([]Account, 0, len(rows))
	for _, row := range rows {
		amount, err := strconv.Atoi(row[2])
		if err != nil {
			return nil, err
		}
		out = append(out, Account{ID: row[0], Customer: row[1], Amount: amount, Status: row[3], Channel: row[4]})
	}
	return out, nil
}

func loadReimbursements(path string) ([]Reimbursement, error) {
	rows, err := readRows(path)
	if err != nil {
		return nil, err
	}
	out := make([]Reimbursement, 0, len(rows))
	for _, row := range rows {
		amount, err := strconv.Atoi(row[2])
		if err != nil {
			return nil, err
		}
		out = append(out, Reimbursement{AccountID: row[0], Customer: row[1], Amount: amount, Channel: row[3]})
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

func writeOutputs(accounts []Account, reimbursements []Reimbursement) error {
	if err := os.MkdirAll("/app/out", 0o755); err != nil {
		return err
	}
	reportPath := filepath.Join("/app/out", "reimbursement_report.csv")
	reportFile, err := os.Create(reportPath)
	if err != nil {
		return err
	}
	defer reportFile.Close()
	writer := csv.NewWriter(reportFile)
	defer writer.Flush()
	if err := writer.Write([]string{"account_id", "customer_id", "channel", "amount_cents", "status"}); err != nil {
		return err
	}

	summary := Summary{}
	for _, reimbursement := range reimbursements {
		match := findMatch(accounts, reimbursement)
		channel := ""
		status := "UNMATCHED"
		if match != nil {
			channel = match.Channel
			status = "MATCHED"
			summary.MatchedCount++
			summary.MatchedAmountCents -= reimbursement.Amount
		} else {
			summary.UnmatchedCount++
			summary.UnmatchedAmountCents += reimbursement.Amount
		}
		if err := writer.Write([]string{
			reimbursement.AccountID,
			reimbursement.Customer,
			channel,
			strconv.Itoa(reimbursement.Amount),
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
	return os.WriteFile("/app/out/reimbursement_summary.json", append(summaryBytes, '\n'), 0o644)
}

func findMatch(accounts []Account, reimbursement Reimbursement) *Account {
	for i := range accounts {
		account := &accounts[i]
		if len(account.ID) >= 8 && len(reimbursement.AccountID) >= 8 &&
			account.ID[:8] == reimbursement.AccountID[:8] &&
			account.Customer == reimbursement.Customer &&
			account.Amount == reimbursement.Amount &&
			account.Status == "POSTED" &&
			allowedChannel(account.Channel) &&
			account.Channel == reimbursement.Channel {
			return account
		}
	}
	return nil
}

func allowedChannel(channel string) bool {
	return channel == "ACH" || channel == "WIRE"
}
