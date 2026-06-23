package main

import (
	"encoding/csv"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strconv"
)

type Membership struct {
	ID       string
	Customer string
	Amount   int
	Status   string
	Program   string
}

type Refund struct {
	MembershipID string
	Customer  string
	Amount    int
	Program    string
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
	memberships, err := loadMemberships("/app/data/memberships.csv")
	if err != nil {
		return err
	}
	refunds, err := loadRefunds("/app/data/refunds.csv")
	if err != nil {
		return err
	}
	return writeOutputs(memberships, refunds)
}

func loadMemberships(path string) ([]Membership, error) {
	rows, err := readRows(path)
	if err != nil {
		return nil, err
	}
	out := make([]Membership, 0, len(rows))
	for _, row := range rows {
		amount, err := strconv.Atoi(row[2])
		if err != nil {
			return nil, err
		}
		out = append(out, Membership{ID: row[0], Customer: row[1], Amount: amount, Status: row[3], Program: row[4]})
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
		out = append(out, Refund{MembershipID: row[0], Customer: row[1], Amount: amount, Program: row[3]})
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

func writeOutputs(memberships []Membership, refunds []Refund) error {
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
	if err := writer.Write([]string{"membership_id", "patron_id", "program", "amount_cents", "status"}); err != nil {
		return err
	}

	summary := Summary{}
	for _, refund := range refunds {
		match := findMatch(memberships, refund)
		program := ""
		status := "UNMATCHED"
		if match != nil {
			program = match.Program
			status = "MATCHED"
			summary.MatchedCount++
			summary.MatchedAmountCents -= refund.Amount
		} else {
			summary.UnmatchedCount++
			summary.UnmatchedAmountCents += refund.Amount
		}
		if err := writer.Write([]string{
			refund.MembershipID,
			refund.Customer,
			program,
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

func findMatch(memberships []Membership, refund Refund) *Membership {
	for i := range memberships {
		membership := &memberships[i]
		if len(membership.ID) >= 8 && len(refund.MembershipID) >= 8 &&
			membership.ID[:8] == refund.MembershipID[:8] &&
			membership.Customer == refund.Customer &&
			membership.Amount == refund.Amount &&
			membership.Status == "ACTIVE" &&
			allowedProgram(membership.Program) &&
			membership.Program == refund.Program {
			return membership
		}
	}
	return nil
}

func allowedProgram(program string) bool {
	return program == "ADULT" || program == "FAMILY" || program == "PATRON"
}
