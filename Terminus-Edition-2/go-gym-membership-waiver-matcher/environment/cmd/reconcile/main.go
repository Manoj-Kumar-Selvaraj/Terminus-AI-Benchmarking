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
	Plan   string
}

type Waiver struct {
	MembershipID string
	Customer  string
	Amount    int
	Plan    string
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
	waivers, err := loadWaivers("/app/data/waivers.csv")
	if err != nil {
		return err
	}
	return writeOutputs(memberships, waivers)
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
		out = append(out, Membership{ID: row[0], Customer: row[1], Amount: amount, Status: row[3], Plan: row[4]})
	}
	return out, nil
}

func loadWaivers(path string) ([]Waiver, error) {
	rows, err := readRows(path)
	if err != nil {
		return nil, err
	}
	out := make([]Waiver, 0, len(rows))
	for _, row := range rows {
		amount, err := strconv.Atoi(row[2])
		if err != nil {
			return nil, err
		}
		out = append(out, Waiver{MembershipID: row[0], Customer: row[1], Amount: amount, Plan: row[3]})
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

func writeOutputs(memberships []Membership, waivers []Waiver) error {
	if err := os.MkdirAll("/app/out", 0o755); err != nil {
		return err
	}
	reportPath := filepath.Join("/app/out", "waiver_report.csv")
	reportFile, err := os.Create(reportPath)
	if err != nil {
		return err
	}
	defer reportFile.Close()
	writer := csv.NewWriter(reportFile)
	defer writer.Flush()
	if err := writer.Write([]string{"membership_id", "member_id", "plan", "amount_cents", "status"}); err != nil {
		return err
	}

	summary := Summary{}
	for _, waiver := range waivers {
		match := findMatch(memberships, waiver)
		plan := ""
		status := "UNMATCHED"
		if match != nil {
			plan = match.Plan
			status = "MATCHED"
			summary.MatchedCount++
			summary.MatchedAmountCents -= waiver.Amount
		} else {
			summary.UnmatchedCount++
			summary.UnmatchedAmountCents += waiver.Amount
		}
		if err := writer.Write([]string{
			waiver.MembershipID,
			waiver.Customer,
			plan,
			strconv.Itoa(waiver.Amount),
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
	return os.WriteFile("/app/out/waiver_summary.json", append(summaryBytes, '\n'), 0o644)
}

func findMatch(memberships []Membership, waiver Waiver) *Membership {
	for i := range memberships {
		membership := &memberships[i]
		if len(membership.ID) >= 8 && len(waiver.MembershipID) >= 8 &&
			membership.ID[:8] == waiver.MembershipID[:8] &&
			membership.Customer == waiver.Customer &&
			membership.Amount == waiver.Amount &&
			membership.Status == "ACTIVE" &&
			allowedPlan(membership.Plan) &&
			membership.Plan == waiver.Plan {
			return membership
		}
	}
	return nil
}

func allowedPlan(plan string) bool {
	return plan == "BASIC" || plan == "PLUS" || plan == "ELITE"
}
