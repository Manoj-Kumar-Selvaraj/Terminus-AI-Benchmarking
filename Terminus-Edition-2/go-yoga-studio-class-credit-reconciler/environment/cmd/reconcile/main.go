package main

import (
	"encoding/csv"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strconv"
)

type Class struct {
	ID       string
	Customer string
	Amount   int
	Status   string
	ClassType   string
}

type Credit struct {
	ClassID string
	Customer  string
	Amount    int
	ClassType    string
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
	classes, err := loadClasses("/app/data/classes.csv")
	if err != nil {
		return err
	}
	credits, err := loadCredits("/app/data/credits.csv")
	if err != nil {
		return err
	}
	return writeOutputs(classes, credits)
}

func loadClasses(path string) ([]Class, error) {
	rows, err := readRows(path)
	if err != nil {
		return nil, err
	}
	out := make([]Class, 0, len(rows))
	for _, row := range rows {
		amount, err := strconv.Atoi(row[2])
		if err != nil {
			return nil, err
		}
		out = append(out, Class{ID: row[0], Customer: row[1], Amount: amount, Status: row[3], ClassType: row[4]})
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
		out = append(out, Credit{ClassID: row[0], Customer: row[1], Amount: amount, ClassType: row[3]})
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

func writeOutputs(classes []Class, credits []Credit) error {
	if err := os.MkdirAll("/app/out", 0o755); err != nil {
		return err
	}
	reportPath := filepath.Join("/app/out", "class_credit_report.csv")
	reportFile, err := os.Create(reportPath)
	if err != nil {
		return err
	}
	defer reportFile.Close()
	writer := csv.NewWriter(reportFile)
	defer writer.Flush()
	if err := writer.Write([]string{"class_id", "member_id", "class_type", "amount_cents", "status"}); err != nil {
		return err
	}

	summary := Summary{}
	for _, credit := range credits {
		match := findMatch(classes, credit)
		class_type := ""
		status := "UNMATCHED"
		if match != nil {
			class_type = match.ClassType
			status = "MATCHED"
			summary.MatchedCount++
			summary.MatchedAmountCents -= credit.Amount
		} else {
			summary.UnmatchedCount++
			summary.UnmatchedAmountCents += credit.Amount
		}
		if err := writer.Write([]string{
			credit.ClassID,
			credit.Customer,
			class_type,
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
	return os.WriteFile("/app/out/class_credit_summary.json", append(summaryBytes, '\n'), 0o644)
}

func findMatch(classes []Class, credit Credit) *Class {
	for i := range classes {
		class := &classes[i]
		if len(class.ID) >= 8 && len(credit.ClassID) >= 8 &&
			class.ID[:8] == credit.ClassID[:8] &&
			class.Customer == credit.Customer &&
			class.Amount == credit.Amount &&
			class.Status == "ACTIVE" &&
			allowedClassType(class.ClassType) &&
			class.ClassType == credit.ClassType {
			return class
		}
	}
	return nil
}

func allowedClassType(class_type string) bool {
	return class_type == "FLOW" || class_type == "POWER" || class_type == "PRIVATE"
}
