package main

import (
	"encoding/csv"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strconv"
)

type Sale struct {
	ID       string
	Customer string
	Amount   int
	Status   string
	Format   string
}

type Credit struct {
	SaleID string
	Customer  string
	Amount    int
	Format    string
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
	sales, err := loadSales("/app/data/sales.csv")
	if err != nil {
		return err
	}
	credits, err := loadCredits("/app/data/credits.csv")
	if err != nil {
		return err
	}
	return writeOutputs(sales, credits)
}

func loadSales(path string) ([]Sale, error) {
	rows, err := readRows(path)
	if err != nil {
		return nil, err
	}
	out := make([]Sale, 0, len(rows))
	for _, row := range rows {
		amount, err := strconv.Atoi(row[2])
		if err != nil {
			return nil, err
		}
		out = append(out, Sale{ID: row[0], Customer: row[1], Amount: amount, Status: row[3], Format: row[4]})
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
		out = append(out, Credit{SaleID: row[0], Customer: row[1], Amount: amount, Format: row[3]})
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

func writeOutputs(sales []Sale, credits []Credit) error {
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
	if err := writer.Write([]string{"sale_id", "buyer_id", "format", "amount_cents", "status"}); err != nil {
		return err
	}

	summary := Summary{}
	for _, credit := range credits {
		match := findMatch(sales, credit)
		format := ""
		status := "UNMATCHED"
		if match != nil {
			format = match.Format
			status = "MATCHED"
			summary.MatchedCount++
			summary.MatchedAmountCents -= credit.Amount
		} else {
			summary.UnmatchedCount++
			summary.UnmatchedAmountCents += credit.Amount
		}
		if err := writer.Write([]string{
			credit.SaleID,
			credit.Customer,
			format,
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

func findMatch(sales []Sale, credit Credit) *Sale {
	for i := range sales {
		sale := &sales[i]
		if len(sale.ID) >= 8 && len(credit.SaleID) >= 8 &&
			sale.ID[:8] == credit.SaleID[:8] &&
			sale.Customer == credit.Customer &&
			sale.Amount == credit.Amount &&
			sale.Status == "SHIPPED" &&
			allowedFormat(sale.Format) &&
			sale.Format == credit.Format {
			return sale
		}
	}
	return nil
}

func allowedFormat(format string) bool {
	return format == "LP" || format == "EP" || format == "BOX"
}
