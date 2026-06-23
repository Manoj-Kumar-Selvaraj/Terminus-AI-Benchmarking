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
	Customer string
	Amount   int
	Status   string
	Service   string
}

type Adjustment struct {
	OrderID string
	Customer  string
	Amount    int
	Service    string
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
	adjustments, err := loadAdjustments("/app/data/adjustments.csv")
	if err != nil {
		return err
	}
	return writeOutputs(orders, adjustments)
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
		out = append(out, Order{ID: row[0], Customer: row[1], Amount: amount, Status: row[3], Service: row[4]})
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
		out = append(out, Adjustment{OrderID: row[0], Customer: row[1], Amount: amount, Service: row[3]})
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

func writeOutputs(orders []Order, adjustments []Adjustment) error {
	if err := os.MkdirAll("/app/out", 0o755); err != nil {
		return err
	}
	reportPath := filepath.Join("/app/out", "adjustment_report.csv")
	reportFile, err := os.Create(reportPath)
	if err != nil {
		return err
	}
	defer reportFile.Close()
	writer := csv.NewWriter(reportFile)
	defer writer.Flush()
	if err := writer.Write([]string{"order_id", "venue_id", "service", "amount_cents", "status"}); err != nil {
		return err
	}

	summary := Summary{}
	for _, adjustment := range adjustments {
		match := findMatch(orders, adjustment)
		service := ""
		status := "UNMATCHED"
		if match != nil {
			service = match.Service
			status = "MATCHED"
			summary.MatchedCount++
			summary.MatchedAmountCents -= adjustment.Amount
		} else {
			summary.UnmatchedCount++
			summary.UnmatchedAmountCents += adjustment.Amount
		}
		if err := writer.Write([]string{
			adjustment.OrderID,
			adjustment.Customer,
			service,
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
	return os.WriteFile("/app/out/adjustment_summary.json", append(summaryBytes, '\n'), 0o644)
}

func findMatch(orders []Order, adjustment Adjustment) *Order {
	for i := range orders {
		order := &orders[i]
		if len(order.ID) >= 8 && len(adjustment.OrderID) >= 8 &&
			order.ID[:8] == adjustment.OrderID[:8] &&
			order.Customer == adjustment.Customer &&
			order.Amount == adjustment.Amount &&
			order.Status == "FULFILLED" &&
			allowedService(order.Service) &&
			order.Service == adjustment.Service {
			return order
		}
	}
	return nil
}

func allowedService(service string) bool {
	return service == "PICKUP" || service == "DELIVERY" || service == "ONSITE"
}
