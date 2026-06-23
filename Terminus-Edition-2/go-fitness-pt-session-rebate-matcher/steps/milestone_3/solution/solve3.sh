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

type Session struct {
	ID         string
	Client      string
	Amount     int
	Status     string
	TrainingType string
	VisitDate  string
}

type Rebate struct {
	SessionID     string
	Client      string
	Amount     int
	TrainingType string
	RebateDate string
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
	sessionHeader, sessionRows, err := readCSV("/app/data/sessions.csv")
	if err != nil {
		return err
	}
	rebateHeader, rebateRows, err := readCSV("/app/data/rebates.csv")
	if err != nil {
		return err
	}
	dated := has(sessionHeader, "session_date") && has(rebateHeader, "rebate_date")
	sessions, err := loadSessions(sessionRows, dated)
	if err != nil {
		return err
	}
	rebates, err := loadRebates(rebateRows, dated)
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
	return writeOutputs(sessions, rebates, openDates, dated)
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

func loadSessions(rows [][]string, dated bool) ([]Session, error) {
	out := make([]Session, 0, len(rows))
	for _, row := range rows {
		amount, err := strconv.Atoi(clean(row[2]))
		if err != nil {
			return nil, err
		}
		session := Session{ID: clean(row[0]), Client: clean(row[1]), Amount: amount, Status: strings.ToUpper(clean(row[3])), TrainingType: canonicalTrainingType(row[4])}
		if dated && len(row) > 5 {
			session.VisitDate = clean(row[5])
		}
		out = append(out, session)
	}
	return out, nil
}

func loadRebates(rows [][]string, dated bool) ([]Rebate, error) {
	out := make([]Rebate, 0, len(rows))
	for _, row := range rows {
		amount, err := strconv.Atoi(clean(row[2]))
		if err != nil {
			return nil, err
		}
		rebate := Rebate{SessionID: clean(row[0]), Client: clean(row[1]), Amount: amount, TrainingType: canonicalTrainingType(row[3])}
		if dated && len(row) > 4 {
			rebate.RebateDate = clean(row[4])
		}
		out = append(out, rebate)
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

func writeOutputs(sessions []Session, rebates []Rebate, openDates map[string]bool, dated bool) error {
	if err := os.MkdirAll("/app/out", 0o755); err != nil {
		return err
	}
	reportPath := filepath.Join("/app/out", "session_rebate_report.csv")
	reportFile, err := os.Create(reportPath)
	if err != nil {
		return err
	}
	defer reportFile.Close()
	writer := csv.NewWriter(reportFile)
	defer writer.Flush()
	if err := writer.Write([]string{"session_id", "client_id", "training_type", "amount_cents", "status"}); err != nil {
		return err
	}

	summary := Summary{}
	used := make([]bool, len(sessions))
	for _, rebate := range rebates {
		matchIndex := findMatch(sessions, rebate, used, openDates, dated)
		accessType := ""
		status := "UNMATCHED"
		if matchIndex >= 0 {
			used[matchIndex] = true
			accessType = sessions[matchIndex].TrainingType
			status = "MATCHED"
			summary.MatchedCount++
			summary.MatchedAmountCents += rebate.Amount
		} else {
			summary.UnmatchedCount++
			summary.UnmatchedAmountCents += rebate.Amount
		}
		if err := writer.Write([]string{rebate.SessionID, rebate.Client, accessType, strconv.Itoa(rebate.Amount), status}); err != nil {
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
	return os.WriteFile("/app/out/session_rebate_summary.json", append(data, '\n'), 0o644)
}

func findMatch(sessions []Session, rebate Rebate, used []bool, openDates map[string]bool, dated bool) int {
	best := -1
	for i := range sessions {
		if used[i] {
			continue
		}
		session := sessions[i]
		if !eligible(session, rebate, openDates, dated) {
			continue
		}
		if !dated {
			return i
		}
		if best < 0 || session.VisitDate > sessions[best].VisitDate || (session.VisitDate == sessions[best].VisitDate && i < best) {
			best = i
		}
	}
	return best
}

func eligible(session Session, rebate Rebate, openDates map[string]bool, dated bool) bool {
	if session.ID != rebate.SessionID || session.Client != rebate.Client || session.Amount != rebate.Amount || session.Status != "ACTIVE" || !allowedTrainingType(session.TrainingType) || session.TrainingType != rebate.TrainingType {
		return false
	}
	if dated {
		if rebate.RebateDate == "" || session.VisitDate == "" || !openDates[rebate.RebateDate] || rebate.RebateDate > session.VisitDate {
			return false
		}
	}
	return true
}

func clean(value string) string {
	return strings.TrimSpace(value)
}

func canonicalTrainingType(accessType string) string {
	switch strings.ToUpper(clean(accessType)) {
	case "SO":
		return "SOLO"
	case "DU":
		return "DUO"
	case "TM":
		return "TEAM"
	default:
		return strings.ToUpper(clean(accessType))
	}
}

func allowedTrainingType(accessType string) bool {
	accessType = canonicalTrainingType(accessType)
	return accessType == "SOLO" || accessType == "DUO" || accessType == "TEAM"
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
test -s /app/out/session_rebate_report.csv
test -s /app/out/session_rebate_summary.json