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

type Appointment struct {
	ID         string
	Patient      string
	Amount     int
	Status     string
	ServiceType string
	VisitDate  string
}

type Credit struct {
	AppointmentID     string
	Patient      string
	Amount     int
	ServiceType string
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
	appointmentHeader, appointmentRows, err := readCSV("/app/data/appointments.csv")
	if err != nil {
		return err
	}
	creditHeader, creditRows, err := readCSV("/app/data/credits.csv")
	if err != nil {
		return err
	}
	dated := has(appointmentHeader, "appointment_date") && has(creditHeader, "credit_date")
	appointments, err := loadAppointments(appointmentRows, dated)
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
	return writeOutputs(appointments, credits, openDates, dated)
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

func loadAppointments(rows [][]string, dated bool) ([]Appointment, error) {
	out := make([]Appointment, 0, len(rows))
	for _, row := range rows {
		amount, err := strconv.Atoi(clean(row[2]))
		if err != nil {
			return nil, err
		}
		appointment := Appointment{ID: clean(row[0]), Patient: clean(row[1]), Amount: amount, Status: strings.ToUpper(clean(row[3])), ServiceType: canonicalServiceType(row[4])}
		if dated && len(row) > 5 {
			appointment.VisitDate = clean(row[5])
		}
		out = append(out, appointment)
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
		credit := Credit{AppointmentID: clean(row[0]), Patient: clean(row[1]), Amount: amount, ServiceType: canonicalServiceType(row[3])}
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

func writeOutputs(appointments []Appointment, credits []Credit, openDates map[string]bool, dated bool) error {
	if err := os.MkdirAll("/app/out", 0o755); err != nil {
		return err
	}
	reportPath := filepath.Join("/app/out", "copay_credit_report.csv")
	reportFile, err := os.Create(reportPath)
	if err != nil {
		return err
	}
	defer reportFile.Close()
	writer := csv.NewWriter(reportFile)
	defer writer.Flush()
	if err := writer.Write([]string{"appointment_id", "patient_id", "service_type", "amount_cents", "status"}); err != nil {
		return err
	}

	summary := Summary{}
	used := make([]bool, len(appointments))
	for _, credit := range credits {
		matchIndex := findMatch(appointments, credit, used, openDates, dated)
		accessType := ""
		status := "UNMATCHED"
		if matchIndex >= 0 {
			used[matchIndex] = true
			accessType = appointments[matchIndex].ServiceType
			status = "MATCHED"
			summary.MatchedCount++
			summary.MatchedAmountCents += credit.Amount
		} else {
			summary.UnmatchedCount++
			summary.UnmatchedAmountCents += credit.Amount
		}
		if err := writer.Write([]string{credit.AppointmentID, credit.Patient, accessType, strconv.Itoa(credit.Amount), status}); err != nil {
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
	return os.WriteFile("/app/out/copay_credit_summary.json", append(data, '\n'), 0o644)
}

func findMatch(appointments []Appointment, credit Credit, used []bool, openDates map[string]bool, dated bool) int {
	best := -1
	for i := range appointments {
		if used[i] {
			continue
		}
		appointment := appointments[i]
		if !eligible(appointment, credit, openDates, dated) {
			continue
		}
		if !dated {
			return i
		}
		if best < 0 || appointment.VisitDate > appointments[best].VisitDate || (appointment.VisitDate == appointments[best].VisitDate && i < best) {
			best = i
		}
	}
	return best
}

func eligible(appointment Appointment, credit Credit, openDates map[string]bool, dated bool) bool {
	if appointment.ID != credit.AppointmentID || appointment.Patient != credit.Patient || appointment.Amount != credit.Amount || appointment.Status != "ACTIVE" || !allowedServiceType(appointment.ServiceType) || appointment.ServiceType != credit.ServiceType {
		return false
	}
	if dated {
		if credit.CreditDate == "" || appointment.VisitDate == "" || !openDates[credit.CreditDate] || credit.CreditDate > appointment.VisitDate {
			return false
		}
	}
	return true
}

func clean(value string) string {
	return strings.TrimSpace(value)
}

func canonicalServiceType(accessType string) string {
	switch strings.ToUpper(clean(accessType)) {
	case "CL":
		return "CLEAN"
	case "XR":
		return "XRAY"
	case "SG":
		return "SURG"
	default:
		return strings.ToUpper(clean(accessType))
	}
}

func allowedServiceType(accessType string) bool {
	accessType = canonicalServiceType(accessType)
	return accessType == "CLEAN" || accessType == "XRAY" || accessType == "SURG"
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
test -s /app/out/copay_credit_report.csv
test -s /app/out/copay_credit_summary.json