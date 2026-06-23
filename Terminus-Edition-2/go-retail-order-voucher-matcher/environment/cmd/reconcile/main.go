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
	Channel   string
}

type Voucher struct {
	OrderID string
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
	orders, err := loadOrders("/app/data/orders.csv")
	if err != nil {
		return err
	}
	vouchers, err := loadVouchers("/app/data/vouchers.csv")
	if err != nil {
		return err
	}
	return writeOutputs(orders, vouchers)
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
		out = append(out, Order{ID: row[0], Customer: row[1], Amount: amount, Status: row[3], Channel: row[4]})
	}
	return out, nil
}

func loadVouchers(path string) ([]Voucher, error) {
	rows, err := readRows(path)
	if err != nil {
		return nil, err
	}
	out := make([]Voucher, 0, len(rows))
	for _, row := range rows {
		amount, err := strconv.Atoi(row[2])
		if err != nil {
			return nil, err
		}
		out = append(out, Voucher{OrderID: row[0], Customer: row[1], Amount: amount, Channel: row[3]})
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

func writeOutputs(orders []Order, vouchers []Voucher) error {
	if err := os.MkdirAll("/app/out", 0o755); err != nil {
		return err
	}
	reportPath := filepath.Join("/app/out", "voucher_report.csv")
	reportFile, err := os.Create(reportPath)
	if err != nil {
		return err
	}
	defer reportFile.Close()
	writer := csv.NewWriter(reportFile)
	defer writer.Flush()
	if err := writer.Write([]string{"order_id", "customer_id", "channel", "amount_cents", "status"}); err != nil {
		return err
	}

	summary := Summary{}
	for _, voucher := range vouchers {
		match := findMatch(orders, voucher)
		channel := ""
		status := "UNMATCHED"
		if match != nil {
			channel = match.Channel
			status = "MATCHED"
			summary.MatchedCount++
			summary.MatchedAmountCents -= voucher.Amount
		} else {
			summary.UnmatchedCount++
			summary.UnmatchedAmountCents += voucher.Amount
		}
		if err := writer.Write([]string{
			voucher.OrderID,
			voucher.Customer,
			channel,
			strconv.Itoa(voucher.Amount),
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
	return os.WriteFile("/app/out/voucher_summary.json", append(summaryBytes, '\n'), 0o644)
}

func findMatch(orders []Order, voucher Voucher) *Order {
	for i := range orders {
		order := &orders[i]
		if len(order.ID) >= 8 && len(voucher.OrderID) >= 8 &&
			order.ID[:8] == voucher.OrderID[:8] &&
			order.Customer == voucher.Customer &&
			order.Amount == voucher.Amount &&
			order.Status == "POSTED" &&
			allowedChannel(order.Channel) &&
			order.Channel == voucher.Channel {
			return order
		}
	}
	return nil
}

func allowedChannel(channel string) bool {
	return channel == "ACH" || channel == "WIRE"
}
