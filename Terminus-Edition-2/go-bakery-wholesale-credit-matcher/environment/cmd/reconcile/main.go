package main

import (
	"encoding/csv"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strconv"
)

type Order struct {
	ID       string
	Cafe     string
	Amount   int
	Status   string
	Route    string
}

type Credit struct {
	OrderID string
	Cafe    string
	Amount  int
	Route   string
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
	orders, err := loadOrders("/app/data/orders.csv")
	if err != nil {
		return err
	}
	credits, err := loadCredits("/app/data/credits.csv")
	if err != nil {
		return err
	}
	return writeOutputs(orders, credits)
}

func loadOrders(path string) ([]Order, error) {
	rows, err := readRows(path)
	if err != nil {
		return nil, err
	}
	out := make([]Order, 0, len(rows))
	for _, row := range rows {
		amount, err := strconv.Atoi(row[2])
		if err != nil {
			return nil, err
		}
		out = append(out, Order{ID: row[0], Cafe: row[1], Amount: amount, Status: row[3], Route: row[4]})
	}
	return out, nil
}

func loadCredits(path string) ([]Credit, error) {
	rows, err := readRows(path)
	if err != nil {
		return nil, err
	}
	out := make([]Credit, 0, len(rows))
	for _, row := range rows {
		amount, err := strconv.Atoi(row[2])
		if err != nil {
			return nil, err
		}
		out = append(out, Credit{OrderID: row[0], Cafe: row[1], Amount: amount, Route: row[3]})
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

func writeOutputs(orders []Order, credits []Credit) error {
	if err := os.MkdirAll("/app/out", 0o755); err != nil {
		return err
	}
	reportPath := filepath.Join("/app/out", "credit_report.csv")
	reportFile, err := os.Create(reportPath)
	if err != nil {
		return err
	}
	defer reportFile.Close()
	writer := csv.NewWriter(reportFile)
	defer writer.Flush()
	if err := writer.Write([]string{"order_id", "cafe_id", "route", "amount_cents", "status"}); err != nil {
		return err
	}

	summary := Summary{}
	for _, credit := range credits {
		match := findMatch(orders, credit)
		route := ""
		status := "UNMATCHED"
		if match != nil {
			route = match.Route
			status = "MATCHED"
			summary.MatchedCount++
			summary.MatchedAmountCents -= credit.Amount
		} else {
			summary.UnmatchedCount++
			summary.UnmatchedAmountCents += credit.Amount
		}
		if err := writer.Write([]string{
			credit.OrderID,
			credit.Cafe,
			route,
			strconv.Itoa(credit.Amount),
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
	return os.WriteFile("/app/out/credit_summary.json", append(summaryBytes, '\n'), 0o644)
}

func findMatch(orders []Order, credit Credit) *Order {
	for i := range orders {
		order := &orders[i]
		if len(order.ID) >= 8 && len(credit.OrderID) >= 8 &&
			order.ID[:8] == credit.OrderID[:8] &&
			order.Cafe == credit.Cafe &&
			order.Amount == credit.Amount &&
			order.Status == "FULFILLED" &&
			allowedRoute(order.Route) &&
			order.Route == credit.Route {
			return order
		}
	}
	return nil
}

func allowedRoute(route string) bool {
	return route == "LOCAL" || route == "REGIONAL" || route == "EXPORT"
}
