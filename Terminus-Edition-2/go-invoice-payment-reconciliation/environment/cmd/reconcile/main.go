package main

import (
	"encoding/csv"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strconv"
)

type Invoice struct {
	ID       string
	Customer string
	Amount   int
	Status   string
	Method   string
}

type Payment struct {
	InvoiceID string
	Customer  string
	Amount    int
	Method    string
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
	invoices, err := loadInvoices("/app/data/invoices.csv")
	if err != nil {
		return err
	}
	payments, err := loadPayments("/app/data/payments.csv")
	if err != nil {
		return err
	}
	return writeOutputs(invoices, payments)
}

func loadInvoices(path string) ([]Invoice, error) {
	rows, err := readRows(path)
	if err != nil {
		return nil, err
	}
	out := make([]Invoice, 0, len(rows))
	for _, row := range rows {
		amount, err := strconv.Atoi(row[2])
		if err != nil {
			return nil, err
		}
		out = append(out, Invoice{ID: row[0], Customer: row[1], Amount: amount, Status: row[3], Method: row[4]})
	}
	return out, nil
}

func loadPayments(path string) ([]Payment, error) {
	rows, err := readRows(path)
	if err != nil {
		return nil, err
	}
	out := make([]Payment, 0, len(rows))
	for _, row := range rows {
		amount, err := strconv.Atoi(row[2])
		if err != nil {
			return nil, err
		}
		out = append(out, Payment{InvoiceID: row[0], Customer: row[1], Amount: amount, Method: row[3]})
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

func writeOutputs(invoices []Invoice, payments []Payment) error {
	if err := os.MkdirAll("/app/out", 0o755); err != nil {
		return err
	}
	reportPath := filepath.Join("/app/out", "payment_report.csv")
	reportFile, err := os.Create(reportPath)
	if err != nil {
		return err
	}
	defer reportFile.Close()
	writer := csv.NewWriter(reportFile)
	defer writer.Flush()
	if err := writer.Write([]string{"invoice_id", "customer_id", "method", "amount_cents", "status"}); err != nil {
		return err
	}

	summary := Summary{}
	for _, payment := range payments {
		match := findMatch(invoices, payment)
		method := ""
		status := "UNMATCHED"
		if match != nil {
			method = match.Method
			status = "MATCHED"
			summary.MatchedCount++
			summary.MatchedAmountCents -= payment.Amount
		} else {
			summary.UnmatchedCount++
			summary.UnmatchedAmountCents += payment.Amount
		}
		if err := writer.Write([]string{
			payment.InvoiceID,
			payment.Customer,
			method,
			strconv.Itoa(payment.Amount),
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
	return os.WriteFile("/app/out/payment_summary.json", append(summaryBytes, '\n'), 0o644)
}

func findMatch(invoices []Invoice, payment Payment) *Invoice {
	for i := range invoices {
		invoice := &invoices[i]
		if len(invoice.ID) >= 8 && len(payment.InvoiceID) >= 8 &&
			invoice.ID[:8] == payment.InvoiceID[:8] &&
			invoice.Customer == payment.Customer &&
			invoice.Amount == payment.Amount &&
			invoice.Status == "POSTED" &&
			allowedMethod(invoice.Method) &&
			invoice.Method == payment.Method {
			return invoice
		}
	}
	return nil
}

func allowedMethod(method string) bool {
	return method == "ACH" || method == "WIRE"
}
