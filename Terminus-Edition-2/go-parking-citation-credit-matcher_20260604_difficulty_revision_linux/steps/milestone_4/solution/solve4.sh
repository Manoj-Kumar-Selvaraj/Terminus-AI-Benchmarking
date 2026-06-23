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

type Citation struct {
	ID       string
	Customer string
	Amount   int
	Status   string
	Zone     string
	DueDate  string
}

type Credit struct {
	CitationID string
	Customer   string
	Amount     int
	Zone       string
	CreditDate string
	Method     string
	HasMethod  bool
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
	citations, err := loadCitations("/app/data/citations.csv")
	if err != nil {
		return err
	}
	credits, err := loadCredits("/app/data/credits.csv")
	if err != nil {
		return err
	}
	openDates, err := loadOpenDates("/app/config/cutoff_calendar.txt")
	if err != nil {
		return err
	}
	enabledMethods, err := loadEnabledMethods("/app/config/methods.csv")
	if err != nil {
		return err
	}
	return writeOutputs(citations, credits, openDates, enabledMethods)
}

func loadCitations(path string) ([]Citation, error) {
	rows, err := readRows(path)
	if err != nil {
		return nil, err
	}
	out := make([]Citation, 0, len(rows))
	for _, row := range rows {
		if len(row) < 5 {
			continue
		}
		amount, err := strconv.Atoi(clean(row[2]))
		if err != nil {
			return nil, err
		}
		dueDate := ""
		if len(row) > 5 {
			dueDate = clean(row[5])
		}
		out = append(out, Citation{
			ID: clean(row[0]), Customer: clean(row[1]), Amount: amount,
			Status: strings.ToUpper(clean(row[3])), Zone: canonicalZone(row[4]), DueDate: dueDate,
		})
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
		if len(row) < 4 {
			continue
		}
		amount, err := strconv.Atoi(clean(row[2]))
		if err != nil {
			return nil, err
		}
		creditDate := ""
		if len(row) > 4 {
			creditDate = clean(row[4])
		}
		method := ""
		hasMethod := len(row) > 5
		if hasMethod {
			method = strings.ToUpper(clean(row[5]))
		}
		out = append(out, Credit{
			CitationID: clean(row[0]), Customer: clean(row[1]), Amount: amount,
			Zone: canonicalZone(row[3]), CreditDate: creditDate, Method: method, HasMethod: hasMethod,
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

func writeOutputs(citations []Citation, credits []Credit, openDates map[string]bool, enabledMethods map[string]bool) error {
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
	if err := writer.Write([]string{"citation_id", "plate_id", "zone", "amount_cents", "status"}); err != nil {
		return err
	}

	summary := Summary{}
	usedCitations := make([]bool, len(citations))
	for _, credit := range credits {
		matchIndex := findMatch(citations, credit, usedCitations, openDates, enabledMethods)
		zone := ""
		status := "UNMATCHED"
		if matchIndex >= 0 {
			match := citations[matchIndex]
			usedCitations[matchIndex] = true
			zone = match.Zone
			status = "MATCHED"
			summary.MatchedCount++
			summary.MatchedAmountCents += credit.Amount
		} else {
			summary.UnmatchedCount++
			summary.UnmatchedAmountCents += credit.Amount
		}
		if err := writer.Write([]string{
			credit.CitationID,
			credit.Customer,
			zone,
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

func findMatch(citations []Citation, credit Credit, used []bool, openDates map[string]bool, enabledMethods map[string]bool) int {
	bestIndex := -1
	for i := range citations {
		if used[i] {
			continue
		}
		citation := &citations[i]
		if !eligibleMethod(credit, enabledMethods) ||
			!openDates[credit.CreditDate] ||
			credit.CreditDate == "" ||
			citation.DueDate == "" ||
			credit.CreditDate > citation.DueDate ||
			citation.ID != credit.CitationID ||
			citation.Customer != credit.Customer ||
			citation.Amount != credit.Amount ||
			citation.Status != "PAID" ||
			!allowedZone(citation.Zone) ||
			citation.Zone != credit.Zone {
			continue
		}
		if bestIndex < 0 || citation.DueDate > citations[bestIndex].DueDate {
			bestIndex = i
		}
	}
	return bestIndex
}

func eligibleMethod(credit Credit, enabledMethods map[string]bool) bool {
	if !credit.HasMethod {
		return true
	}
	return credit.Method != "" && enabledMethods[credit.Method]
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

func loadEnabledMethods(path string) (map[string]bool, error) {
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
	enabled := map[string]bool{}
	for _, row := range rows[1:] {
		if len(row) < 2 {
			continue
		}
		method := strings.ToUpper(clean(row[0]))
		if method == "" {
			continue
		}
		if strings.EqualFold(clean(row[1]), "true") {
			enabled[method] = true
		}
	}
	return enabled, nil
}

func clean(value string) string {
	return strings.TrimSpace(value)
}

func canonicalZone(zone string) string {
	switch strings.ToUpper(clean(zone)) {
	case "ST":
		return "STREET"
	case "GRG":
		return "GARAGE"
	case "LT":
		return "LOT"
	default:
		return strings.ToUpper(clean(zone))
	}
}

func allowedZone(zone string) bool {
	zone = canonicalZone(zone)
	return zone == "STREET" || zone == "GARAGE" || zone == "LOT"
}
GO

/app/scripts/run_batch.sh
test -s /app/out/credit_report.csv
test -s /app/out/credit_summary.json
