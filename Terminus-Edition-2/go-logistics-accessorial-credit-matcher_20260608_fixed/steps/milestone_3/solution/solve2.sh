#!/usr/bin/env bash
set -euo pipefail

cat > /app/cmd/reconcile/main.go <<'GO'
package main

import (
	"encoding/csv"
	"encoding/json"
	"os"
	"strconv"
	"strings"
)

type Charge struct {
	ID          string
	Shipper    string
	Amount      int
	Status      string
	Mode        string
	InvoiceDate string
}

type Credit struct {
	ChargeID   string
	Shipper    string
	Amount     int
	Mode       string
	CreditDate string
}

type Summary struct {
	MatchedCount         int `json:"matched_count"`
	MatchedAmountCents   int `json:"matched_amount_cents"`
	UnmatchedCount       int `json:"unmatched_count"`
	UnmatchedAmountCents int `json:"unmatched_amount_cents"`
}

func main() {
	if err := run(); err != nil {
		panic(err)
	}
}

func run() error {
	charges, hasInvoiceDate, err := loadCharges("/app/data/charges.csv")
	if err != nil {
		return err
	}
	credits, hasCreditDate, err := loadCredits("/app/data/credits.csv")
	if err != nil {
		return err
	}
	openDates, _ := loadOpenDates("/app/config/cutoff_calendar.txt")
	return writeOutputs(charges, credits, openDates, hasInvoiceDate && hasCreditDate)
}

func loadCharges(path string) ([]Charge, bool, error) {
	records, hasInvoiceDate, err := readCSV(path, "invoice_date")
	if err != nil {
		return nil, false, err
	}
	charges := make([]Charge, 0, len(records))
	for _, row := range records {
		amount, err := strconv.Atoi(clean(row["amount_cents"]))
		if err != nil {
			return nil, false, err
		}
		charges = append(charges, Charge{
			ID:          clean(row["charge_id"]),
			Shipper:     clean(row["shipper_id"]),
			Amount:      amount,
			Status:      strings.ToUpper(clean(row["status"])),
			Mode:        canonicalMode(row["mode"]),
			InvoiceDate: clean(row["invoice_date"]),
		})
	}
	return charges, hasInvoiceDate, nil
}

func loadCredits(path string) ([]Credit, bool, error) {
	records, hasCreditDate, err := readCSV(path, "credit_date")
	if err != nil {
		return nil, false, err
	}
	credits := make([]Credit, 0, len(records))
	for _, row := range records {
		amount, err := strconv.Atoi(clean(row["amount_cents"]))
		if err != nil {
			return nil, false, err
		}
		credits = append(credits, Credit{
			ChargeID:   clean(row["charge_id"]),
			Shipper:    clean(row["shipper_id"]),
			Amount:     amount,
			Mode:       canonicalMode(row["mode"]),
			CreditDate: clean(row["credit_date"]),
		})
	}
	return credits, hasCreditDate, nil
}

func readCSV(path string, optionalColumn string) ([]map[string]string, bool, error) {
	file, err := os.Open(path)
	if err != nil {
		return nil, false, err
	}
	defer file.Close()
	reader := csv.NewReader(file)
	reader.FieldsPerRecord = -1
	rows, err := reader.ReadAll()
	if err != nil || len(rows) == 0 {
		return nil, false, err
	}
	headers := rows[0]
	hasOptional := false
	for _, header := range headers {
		if clean(header) == optionalColumn {
			hasOptional = true
			break
		}
	}
	out := make([]map[string]string, 0, len(rows)-1)
	for _, values := range rows[1:] {
		row := map[string]string{}
		for i, header := range headers {
			value := ""
			if i < len(values) {
				value = values[i]
			}
			row[clean(header)] = value
		}
		out = append(out, row)
	}
	return out, hasOptional, nil
}

func loadOpenDates(path string) (map[string]bool, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return map[string]bool{}, err
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

func writeOutputs(charges []Charge, credits []Credit, openDates map[string]bool, datedMode bool) error {
	used := make([]bool, len(charges))
	reportRows := make([][]string, 0, len(credits))
	summary := Summary{}
	for _, credit := range credits {
		matchIndex := findMatch(charges, credit, used, openDates, datedMode)
		mode := ""
		status := "UNMATCHED"
		if matchIndex >= 0 {
			used[matchIndex] = true
			mode = charges[matchIndex].Mode
			status = "MATCHED"
			summary.MatchedCount++
			summary.MatchedAmountCents += credit.Amount
		} else {
			summary.UnmatchedCount++
			summary.UnmatchedAmountCents += credit.Amount
		}
		reportRows = append(reportRows, []string{credit.ChargeID, credit.Shipper, mode, strconv.Itoa(credit.Amount), status})
	}
	if err := os.MkdirAll("/app/out", 0o755); err != nil {
		return err
	}
	if err := writeReport("/app/out/credit_report.csv", reportRows); err != nil {
		return err
	}
	return writeSummary("/app/out/credit_summary.json", summary)
}

func findMatch(charges []Charge, credit Credit, used []bool, openDates map[string]bool, datedMode bool) int {
	best := -1
	for i := range charges {
		if used[i] {
			continue
		}
		charge := charges[i]
		if charge.ID != credit.ChargeID ||
			charge.Shipper != credit.Shipper ||
			charge.Amount != credit.Amount ||
			charge.Status != "BILLED" ||
			!allowedMode(charge.Mode) ||
			charge.Mode != credit.Mode {
			continue
		}
		if !datedMode {
			return i
		}
		if credit.CreditDate == "" || charge.InvoiceDate == "" || !openDates[credit.CreditDate] || credit.CreditDate > charge.InvoiceDate {
			continue
		}
		if best < 0 || charge.InvoiceDate > charges[best].InvoiceDate {
			best = i
		}
	}
	return best
}

func writeReport(path string, rows [][]string) error {
	file, err := os.Create(path)
	if err != nil {
		return err
	}
	defer file.Close()
	writer := csv.NewWriter(file)
	defer writer.Flush()
	if err := writer.Write([]string{"charge_id", "shipper_id", "mode", "amount_cents", "status"}); err != nil {
		return err
	}
	for _, row := range rows {
		if err := writer.Write(row); err != nil {
			return err
		}
	}
	return writer.Error()
}

func writeSummary(path string, summary Summary) error {
	data, err := json.Marshal(summary)
	if err != nil {
		return err
	}
	return os.WriteFile(path, data, 0o644)
}

func clean(value string) string {
	return strings.TrimSpace(value)
}

func canonicalMode(value string) string {
	switch strings.ToUpper(clean(value)) {
	case "LESS":
		return "LTL"
	case "FULL":
		return "FTL"
	case "RR":
		return "RAIL"
	default:
		return strings.ToUpper(clean(value))
	}
}

func allowedMode(mode string) bool {
	switch mode {
	case "LTL", "FTL", "RAIL":
		return true
	default:
		return false
	}
}
GO

/app/scripts/run_batch.sh
test -s /app/out/credit_report.csv
test -s /app/out/credit_summary.json
