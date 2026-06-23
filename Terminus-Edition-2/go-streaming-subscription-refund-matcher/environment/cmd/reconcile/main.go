package main

import (
	"encoding/csv"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strconv"
)

type Subscription struct {
	ID       string
	Customer string
	Amount   int
	Status   string
	Plan   string
}

type Refund struct {
	SubscriptionID string
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
	subscriptions, err := loadSubscriptions("/app/data/subscriptions.csv")
	if err != nil {
		return err
	}
	refunds, err := loadRefunds("/app/data/refunds.csv")
	if err != nil {
		return err
	}
	return writeOutputs(subscriptions, refunds)
}

func loadSubscriptions(path string) ([]Subscription, error) {
	rows, err := readRows(path)
	if err != nil {
		return nil, err
	}
	out := make([]Subscription, 0, len(rows))
	for _, row := range rows {
		amount, err := strconv.Atoi(row[2])
		if err != nil {
			return nil, err
		}
		out = append(out, Subscription{ID: row[0], Customer: row[1], Amount: amount, Status: row[3], Plan: row[4]})
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
		out = append(out, Refund{SubscriptionID: row[0], Customer: row[1], Amount: amount, Plan: row[3]})
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

func writeOutputs(subscriptions []Subscription, refunds []Refund) error {
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
	if err := writer.Write([]string{"subscription_id", "subscriber_id", "plan", "amount_cents", "status"}); err != nil {
		return err
	}

	summary := Summary{}
	for _, refund := range refunds {
		match := findMatch(subscriptions, refund)
		plan := ""
		status := "UNMATCHED"
		if match != nil {
			plan = match.Plan
			status = "MATCHED"
			summary.MatchedCount++
			summary.MatchedAmountCents -= refund.Amount
		} else {
			summary.UnmatchedCount++
			summary.UnmatchedAmountCents += refund.Amount
		}
		if err := writer.Write([]string{
			refund.SubscriptionID,
			refund.Customer,
			plan,
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

func findMatch(subscriptions []Subscription, refund Refund) *Subscription {
	for i := range subscriptions {
		subscription := &subscriptions[i]
		if len(subscription.ID) >= 8 && len(refund.SubscriptionID) >= 8 &&
			subscription.ID[:8] == refund.SubscriptionID[:8] &&
			subscription.Customer == refund.Customer &&
			subscription.Amount == refund.Amount &&
			subscription.Status == "ACTIVE" &&
			allowedPlan(subscription.Plan) &&
			subscription.Plan == refund.Plan {
			return subscription
		}
	}
	return nil
}

func allowedPlan(plan string) bool {
	return plan == "BASIC" || plan == "FAMILY" || plan == "PREMIUM"
}
