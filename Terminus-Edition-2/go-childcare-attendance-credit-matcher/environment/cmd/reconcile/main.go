package main

import (
	"encoding/csv"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strconv"
)

type Attendance struct {
	ID       string
	Customer string
	Amount   int
	Status   string
	CareType   string
}

type Credit struct {
	AttendanceID string
	Customer  string
	Amount    int
	CareType    string
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
	attendances, err := loadAttendances("/app/data/attendances.csv")
	if err != nil {
		return err
	}
	credits, err := loadCredits("/app/data/credits.csv")
	if err != nil {
		return err
	}
	return writeOutputs(attendances, credits)
}

func loadAttendances(path string) ([]Attendance, error) {
	rows, err := readRows(path)
	if err != nil {
		return nil, err
	}
	out := make([]Attendance, 0, len(rows))
	for _, row := range rows {
		amount, err := strconv.Atoi(row[2])
		if err != nil {
			return nil, err
		}
		out = append(out, Attendance{ID: row[0], Customer: row[1], Amount: amount, Status: row[3], CareType: row[4]})
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
		out = append(out, Credit{AttendanceID: row[0], Customer: row[1], Amount: amount, CareType: row[3]})
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

func writeOutputs(attendances []Attendance, credits []Credit) error {
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
	for _, credit := range credits {
		match := findMatch(attendances, credit)
		care_type := ""
		status := "UNMATCHED"
		if match != nil {
			care_type = match.CareType
			status = "MATCHED"
			summary.MatchedCount++
			summary.MatchedAmountCents -= credit.Amount
		} else {
			summary.UnmatchedCount++
			summary.UnmatchedAmountCents += credit.Amount
		}
		if err := writer.Write([]string{
			credit.AttendanceID,
			credit.Customer,
			care_type,
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
	return os.WriteFile("/app/out/attendance_credit_summary.json", append(summaryBytes, '\n'), 0o644)
}

func findMatch(attendances []Attendance, credit Credit) *Attendance {
	for i := range attendances {
		attendance := &attendances[i]
		if len(attendance.ID) >= 8 && len(credit.AttendanceID) >= 8 &&
			attendance.ID[:8] == credit.AttendanceID[:8] &&
			attendance.Customer == credit.Customer &&
			attendance.Amount == credit.Amount &&
			attendance.Status == "ACTIVE" &&
			allowedCareType(attendance.CareType) &&
			attendance.CareType == credit.CareType {
			return attendance
		}
	}
	return nil
}

func allowedCareType(care_type string) bool {
	return care_type == "HALF" || care_type == "FULL" || care_type == "EXT"
}
