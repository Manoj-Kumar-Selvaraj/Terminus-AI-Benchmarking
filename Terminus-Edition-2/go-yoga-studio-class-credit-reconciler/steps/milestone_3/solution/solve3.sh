#!/usr/bin/env bash
set -euo pipefail

cd /app

cat > /app/cmd/reconcile/main.go <<'GO'
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

type Class struct {
	ID         string
	Member      string
	Amount     int
	Status     string
	ClassType string
	VisitDate  string
}

type Credit struct {
	ClassID     string
	Member      string
	Amount     int
	ClassType string
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
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}

func run() error {
	classHeader, classRows, err := readCSV("/app/data/classes.csv")
	if err != nil {
		return err
	}
	creditHeader, creditRows, err := readCSV("/app/data/credits.csv")
	if err != nil {
		return err
	}
	dated := has(classHeader, "class_date") && has(creditHeader, "credit_date")
	classes, err := loadClasses(classRows, dated)
	if err != nil {
		return err
	}
	credits, err := loadCredits(creditRows, dated)
	if err != nil {
		return err
	}
	openDates := map[string]bool{}
	if dated {
		openDates, err = loadOpenDates("/app/config/cutoff_calendar.txt")
		if err != nil {
			return err
		}
	}
	return writeOutputs(classes, credits, openDates, dated)
}

func readCSV(path string) ([]string, [][]string, error) {
	f, err := os.Open(path)
	if err != nil {
		return nil, nil, err
	}
	defer f.Close()
	reader := csv.NewReader(f)
	reader.FieldsPerRecord = -1
	rows, err := reader.ReadAll()
	if err != nil {
		return nil, nil, err
	}
	if len(rows) == 0 {
		return nil, nil, nil
	}
	return rows[0], rows[1:], nil
}

func loadClasses(rows [][]string, dated bool) ([]Class, error) {
	out := make([]Class, 0, len(rows))
	for _, row := range rows {
		amount, err := strconv.Atoi(clean(row[2]))
		if err != nil {
			return nil, err
		}
		class := Class{ID: clean(row[0]), Member: clean(row[1]), Amount: amount, Status: strings.ToUpper(clean(row[3])), ClassType: canonicalClassType(row[4])}
		if dated && len(row) > 5 {
			class.VisitDate = clean(row[5])
		}
		out = append(out, class)
	}
	return out, nil
}

func loadCredits(rows [][]string, dated bool) ([]Credit, error) {
	out := make([]Credit, 0, len(rows))
	for _, row := range rows {
		amount, err := strconv.Atoi(clean(row[2]))
		if err != nil {
			return nil, err
		}
		credit := Credit{ClassID: clean(row[0]), Member: clean(row[1]), Amount: amount, ClassType: canonicalClassType(row[3])}
		if dated && len(row) > 4 {
			credit.CreditDate = clean(row[4])
		}
		out = append(out, credit)
	}
	return out, nil
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

func writeOutputs(classes []Class, credits []Credit, openDates map[string]bool, dated bool) error {
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
	used := make([]bool, len(classes))
	for _, credit := range credits {
		matchIndex := findMatch(classes, credit, used, openDates, dated)
		accessType := ""
		status := "UNMATCHED"
		if matchIndex >= 0 {
			used[matchIndex] = true
			accessType = classes[matchIndex].ClassType
			status = "MATCHED"
			summary.MatchedCount++
			summary.MatchedAmountCents += credit.Amount
		} else {
			summary.UnmatchedCount++
			summary.UnmatchedAmountCents += credit.Amount
		}
		if err := writer.Write([]string{credit.ClassID, credit.Member, accessType, strconv.Itoa(credit.Amount), status}); err != nil {
			return err
		}
	}
	if writer.Error() != nil {
		return writer.Error()
	}
	data, err := json.MarshalIndent(summary, "", "  ")
	if err != nil {
		return err
	}
	return os.WriteFile("/app/out/class_credit_summary.json", append(data, '\n'), 0o644)
}

func findMatch(classes []Class, credit Credit, used []bool, openDates map[string]bool, dated bool) int {
	best := -1
	for i := range classes {
		if used[i] {
			continue
		}
		class := classes[i]
		if !eligible(class, credit, openDates, dated) {
			continue
		}
		if !dated {
			return i
		}
		if best < 0 || class.VisitDate > classes[best].VisitDate || (class.VisitDate == classes[best].VisitDate && i < best) {
			best = i
		}
	}
	return best
}

func eligible(class Class, credit Credit, openDates map[string]bool, dated bool) bool {
	if class.ID != credit.ClassID || class.Member != credit.Member || class.Amount != credit.Amount || class.Status != "ACTIVE" || !allowedClassType(class.ClassType) || class.ClassType != credit.ClassType {
		return false
	}
	if dated {
		if credit.CreditDate == "" || class.VisitDate == "" || !openDates[credit.CreditDate] || credit.CreditDate > class.VisitDate {
			return false
		}
	}
	return true
}

func clean(value string) string {
	return strings.TrimSpace(value)
}

func canonicalClassType(accessType string) string {
	switch strings.ToUpper(clean(accessType)) {
	case "FL":
		return "FLOW"
	case "PW":
		return "POWER"
	case "PR":
		return "PRIVATE"
	default:
		return strings.ToUpper(clean(accessType))
	}
}

func allowedClassType(accessType string) bool {
	accessType = canonicalClassType(accessType)
	return accessType == "FLOW" || accessType == "POWER" || accessType == "PRIVATE"
}

func has(headers []string, name string) bool {
	for _, header := range headers {
		if strings.EqualFold(clean(header), name) {
			return true
		}
	}
	return false
}
GO

/app/scripts/run_batch.sh
test -s /app/out/class_credit_report.csv
test -s /app/out/class_credit_summary.json