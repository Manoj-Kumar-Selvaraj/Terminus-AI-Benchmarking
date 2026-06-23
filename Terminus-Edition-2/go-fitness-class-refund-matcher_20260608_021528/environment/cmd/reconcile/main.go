package main

import (
	"encoding/csv"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strconv"
)

type Classpass struct {
	ID       string
	Customer string
	Amount   int
	Status   string
	Studio   string
}

type Refund struct {
	ClasspassID string
	Customer  string
	Amount    int
	Studio    string
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
	classpasses, err := loadClasspasses("/app/data/classes.csv")
	if err != nil {
		return err
	}
	refunds, err := loadRefunds("/app/data/refunds.csv")
	if err != nil {
		return err
	}
	return writeOutputs(classpasses, refunds)
}

func loadClasspasses(path string) ([]Classpass, error) {
	rows, err := readRows(path)
	if err != nil {
		return nil, err
	}
	out := make([]Classpass, 0, len(rows))
	for _, row := range rows {
		amount, err := strconv.Atoi(row[2])
		if err != nil {
			return nil, err
		}
		out = append(out, Classpass{ID: row[0], Customer: row[1], Amount: amount, Status: row[3], Studio: row[4]})
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
		out = append(out, Refund{ClasspassID: row[0], Customer: row[1], Amount: amount, Studio: row[3]})
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

func writeOutputs(classpasses []Classpass, refunds []Refund) error {
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
	if err := writer.Write([]string{"class_id", "member_id", "studio", "amount_cents", "status"}); err != nil {
		return err
	}

	summary := Summary{}
	for _, refund := range refunds {
		match := findMatch(classpasses, refund)
		studio := ""
		status := "UNMATCHED"
		if match != nil {
			studio = match.Studio
			status = "MATCHED"
			summary.MatchedCount++
			summary.MatchedAmountCents -= refund.Amount
		} else {
			summary.UnmatchedCount++
			summary.UnmatchedAmountCents += refund.Amount
		}
		if err := writer.Write([]string{
			refund.ClasspassID,
			refund.Customer,
			studio,
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

func findMatch(classpasses []Classpass, refund Refund) *Classpass {
	for i := range classpasses {
		classpass := &classpasses[i]
		if len(classpass.ID) >= 8 && len(refund.ClasspassID) >= 8 &&
			classpass.ID[:8] == refund.ClasspassID[:8] &&
			classpass.Customer == refund.Customer &&
			classpass.Amount == refund.Amount &&
			classpass.Status == "BOOKED" &&
			allowedStudio(classpass.Studio) &&
			classpass.Studio == refund.Studio {
			return classpass
		}
	}
	return nil
}

func allowedStudio(studio string) bool {
	return studio == "YOGA" || studio == "SPIN" || studio == "HIIT"
}
