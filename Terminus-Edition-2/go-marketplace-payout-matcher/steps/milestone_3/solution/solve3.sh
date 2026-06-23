#!/usr/bin/env bash
set -euo pipefail

cd /app

cat > /app/cmd/reconcile/main.go <<'EOF'
package main

import (
	"encoding/csv"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strconv"
	"strings"
)

type Order struct {
	ID       string
	Customer string
	Amount   int
	Status   string
	Lane     string
	ShipDate string
}

type Payout struct {
	OrderID    string
	Customer   string
	Amount     int
	Lane       string
	PayoutDate string
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
	payouts, err := loadPayouts("/app/data/payouts.csv")
	if err != nil {
		return err
	}
	openDates, err := loadOpenDates("/app/config/cutoff_calendar.txt")
	if err != nil {
		return err
	}
	return writeOutputs(orders, payouts, openDates)
}

func loadOrders(path string) ([]Order, error) {
	rows, err := readRows(path)
	if err != nil {
		return nil, err
	}
	out := make([]Order, 0, len(rows))
	for _, row := range rows {
		amount, err := strconv.Atoi(clean(row[2]))
		if err != nil {
			return nil, err
		}
		shipDate := ""
		if len(row) > 5 {
			shipDate = clean(row[5])
		}
		out = append(out, Order{
			ID:       clean(row[0]),
			Customer: clean(row[1]),
			Amount:   amount,
			Status:   strings.ToUpper(clean(row[3])),
			Lane:     canonicalLane(row[4]),
			ShipDate: shipDate,
		})
	}
	return out, nil
}

func loadPayouts(path string) ([]Payout, error) {
	rows, err := readRows(path)
	if err != nil {
		return nil, err
	}
	out := make([]Payout, 0, len(rows))
	for _, row := range rows {
		amount, err := strconv.Atoi(clean(row[2]))
		if err != nil {
			return nil, err
		}
		payoutDate := ""
		if len(row) > 4 {
			payoutDate = clean(row[4])
		}
		out = append(out, Payout{
			OrderID:    clean(row[0]),
			Customer:   clean(row[1]),
			Amount:     amount,
			Lane:       canonicalLane(row[3]),
			PayoutDate: payoutDate,
		})
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

func writeOutputs(orders []Order, payouts []Payout, openDates map[string]bool) error {
	if err := os.MkdirAll("/app/out", 0o755); err != nil {
		return err
	}
	reportPath := filepath.Join("/app/out", "payout_report.csv")
	reportFile, err := os.Create(reportPath)
	if err != nil {
		return err
	}
	defer reportFile.Close()
	writer := csv.NewWriter(reportFile)
	defer writer.Flush()
	if err := writer.Write([]string{"order_id", "seller_id", "lane", "amount_cents", "status"}); err != nil {
		return err
	}

	summary := Summary{}
	usedOrders := make([]bool, len(orders))
	for _, payout := range payouts {
		matchIndex := findMatch(orders, payout, usedOrders, openDates)
		lane := ""
		status := "UNMATCHED"
		if matchIndex >= 0 {
			match := &orders[matchIndex]
			usedOrders[matchIndex] = true
			lane = match.Lane
			status = "MATCHED"
			summary.MatchedCount++
			summary.MatchedAmountCents += payout.Amount
		} else {
			summary.UnmatchedCount++
			summary.UnmatchedAmountCents += payout.Amount
		}
		if err := writer.Write([]string{
			payout.OrderID,
			payout.Customer,
			lane,
			strconv.Itoa(payout.Amount),
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
	return os.WriteFile("/app/out/payout_summary.json", append(summaryBytes, '\n'), 0o644)
}

func findMatch(orders []Order, payout Payout, used []bool, openDates map[string]bool) int {
	bestIndex := -1
	for i := range orders {
		if used[i] {
			continue
		}
		order := &orders[i]
		if order.ID != payout.OrderID ||
			order.Customer != payout.Customer ||
			order.Amount != payout.Amount ||
			order.Status != "SHIPPED" ||
			!allowedLane(order.Lane) ||
			order.Lane != payout.Lane {
			continue
		}

		if payout.PayoutDate == "" ||
			order.ShipDate == "" ||
			!openDates[payout.PayoutDate] ||
			payout.PayoutDate > order.ShipDate {
			continue
		}

		if bestIndex < 0 || order.ShipDate > orders[bestIndex].ShipDate {
			bestIndex = i
		}
	}
	return bestIndex
}

func loadOpenDates(path string) (map[string]bool, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	openDates := map[string]bool{}
	for _, line := range strings.Split(string(data), "\n") {
		fields := strings.Fields(line)
		if len(fields) >= 2 && strings.EqualFold(fields[1], "open") {
			openDates[fields[0]] = true
		}
	}
	return openDates, nil
}

func clean(value string) string {
	return strings.TrimSpace(value)
}

func canonicalLane(lane string) string {
	switch strings.ToUpper(clean(lane)) {
	case "DRP":
		return "D2D"
	case "PKU":
		return "LOCKER"
	case "RTL":
		return "STORE"
	default:
		return strings.ToUpper(clean(lane))
	}
}

func allowedLane(lane string) bool {
	lane = canonicalLane(lane)
	return lane == "D2D" || lane == "LOCKER" || lane == "STORE"
}
EOF

/app/scripts/run_batch.sh
test -s /app/out/payout_report.csv
test -s /app/out/payout_summary.json
