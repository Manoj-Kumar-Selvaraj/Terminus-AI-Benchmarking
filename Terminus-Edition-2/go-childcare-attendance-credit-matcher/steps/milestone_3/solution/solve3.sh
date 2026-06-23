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

type Attendance struct {
	ID         string
	Child      string
	Amount     int
	Status     string
	CareType string
	VisitDate  string
}

type Credit struct {
	AttendanceID     string
	Child      string
	Amount     int
	CareType string
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
	attendanceHeader, attendanceRows, err := readCSV("/app/data/attendances.csv")
	if err != nil {
		return err
	}
	creditHeader, creditRows, err := readCSV("/app/data/credits.csv")
	if err != nil {
		return err
	}
	dated := has(attendanceHeader, "attendance_date") && has(creditHeader, "credit_date")
	attendances, err := loadAttendances(attendanceRows, dated)
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
	return writeOutputs(attendances, credits, openDates, dated)
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

func loadAttendances(rows [][]string, dated bool) ([]Attendance, error) {
	out := make([]Attendance, 0, len(rows))
	for _, row := range rows {
		amount, err := strconv.Atoi(clean(row[2]))
		if err != nil {
			return nil, err
		}
		attendance := Attendance{ID: clean(row[0]), Child: clean(row[1]), Amount: amount, Status: strings.ToUpper(clean(row[3])), CareType: canonicalCareType(row[4])}
		if dated && len(row) > 5 {
			attendance.VisitDate = clean(row[5])
		}
		out = append(out, attendance)
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
		credit := Credit{AttendanceID: clean(row[0]), Child: clean(row[1]), Amount: amount, CareType: canonicalCareType(row[3])}
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

func writeOutputs(attendances []Attendance, credits []Credit, openDates map[string]bool, dated bool) error {
	if err := os.MkdirAll("/app/out", 0o755); err != nil {
		return err
	}
	reportPath := filepath.Join("/app/out", "attendance_credit_report.csv")
	reportFile, err := os.Create(reportPath)
	if err != nil {
		return err
	}
	defer reportFile.Close()
	writer := csv.NewWriter(reportFile)
	defer writer.Flush()
	if err := writer.Write([]string{"attendance_id", "child_id", "care_type", "amount_cents", "status"}); err != nil {
		return err
	}

	summary := Summary{}
	used := make([]bool, len(attendances))
	for _, credit := range credits {
		matchIndex := findMatch(attendances, credit, used, openDates, dated)
		accessType := ""
		status := "UNMATCHED"
		if matchIndex >= 0 {
			used[matchIndex] = true
			accessType = attendances[matchIndex].CareType
			status = "MATCHED"
			summary.MatchedCount++
			summary.MatchedAmountCents += credit.Amount
		} else {
			summary.UnmatchedCount++
			summary.UnmatchedAmountCents += credit.Amount
		}
		if err := writer.Write([]string{credit.AttendanceID, credit.Child, accessType, strconv.Itoa(credit.Amount), status}); err != nil {
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
	return os.WriteFile("/app/out/attendance_credit_summary.json", append(data, '\n'), 0o644)
}

func findMatch(attendances []Attendance, credit Credit, used []bool, openDates map[string]bool, dated bool) int {
	best := -1
	for i := range attendances {
		if used[i] {
			continue
		}
		attendance := attendances[i]
		if !eligible(attendance, credit, openDates, dated) {
			continue
		}
		if !dated {
			return i
		}
		if best < 0 || attendance.VisitDate > attendances[best].VisitDate || (attendance.VisitDate == attendances[best].VisitDate && i < best) {
			best = i
		}
	}
	return best
}

func eligible(attendance Attendance, credit Credit, openDates map[string]bool, dated bool) bool {
	if attendance.ID != credit.AttendanceID || attendance.Child != credit.Child || attendance.Amount != credit.Amount || attendance.Status != "ACTIVE" || !allowedCareType(attendance.CareType) || attendance.CareType != credit.CareType {
		return false
	}
	if dated {
		if credit.CreditDate == "" || attendance.VisitDate == "" || !openDates[credit.CreditDate] || credit.CreditDate > attendance.VisitDate {
			return false
		}
	}
	return true
}

func clean(value string) string {
	return strings.TrimSpace(value)
}

func canonicalCareType(accessType string) string {
	switch strings.ToUpper(clean(accessType)) {
	case "HF":
		return "HALF"
	case "FD":
		return "FULL"
	case "EX":
		return "EXT"
	default:
		return strings.ToUpper(clean(accessType))
	}
}

func allowedCareType(accessType string) bool {
	accessType = canonicalCareType(accessType)
	return accessType == "HALF" || accessType == "FULL" || accessType == "EXT"
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
test -s /app/out/attendance_credit_report.csv
test -s /app/out/attendance_credit_summary.json