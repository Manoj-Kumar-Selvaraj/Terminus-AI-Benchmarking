package main

import (
	"encoding/csv"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strconv"
)

type Appointment struct {
	ID       string
	Customer string
	Amount   int
	Status   string
	ServiceType   string
}

type Credit struct {
	AppointmentID string
	Customer  string
	Amount    int
	ServiceType    string
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
	appointments, err := loadAppointments("/app/data/appointments.csv")
	if err != nil {
		return err
	}
	credits, err := loadCredits("/app/data/credits.csv")
	if err != nil {
		return err
	}
	return writeOutputs(appointments, credits)
}

func loadAppointments(path string) ([]Appointment, error) {
	rows, err := readRows(path)
	if err != nil {
		return nil, err
	}
	out := make([]Appointment, 0, len(rows))
	for _, row := range rows {
		amount, err := strconv.Atoi(row[2])
		if err != nil {
			return nil, err
		}
		out = append(out, Appointment{ID: row[0], Customer: row[1], Amount: amount, Status: row[3], ServiceType: row[4]})
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
		out = append(out, Credit{AppointmentID: row[0], Customer: row[1], Amount: amount, ServiceType: row[3]})
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

func writeOutputs(appointments []Appointment, credits []Credit) error {
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
	for _, credit := range credits {
		match := findMatch(appointments, credit)
		service_type := ""
		status := "UNMATCHED"
		if match != nil {
			service_type = match.ServiceType
			status = "MATCHED"
			summary.MatchedCount++
			summary.MatchedAmountCents -= credit.Amount
		} else {
			summary.UnmatchedCount++
			summary.UnmatchedAmountCents += credit.Amount
		}
		if err := writer.Write([]string{
			credit.AppointmentID,
			credit.Customer,
			service_type,
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
	return os.WriteFile("/app/out/copay_credit_summary.json", append(summaryBytes, '\n'), 0o644)
}

func findMatch(appointments []Appointment, credit Credit) *Appointment {
	for i := range appointments {
		appointment := &appointments[i]
		if len(appointment.ID) >= 8 && len(credit.AppointmentID) >= 8 &&
			appointment.ID[:8] == credit.AppointmentID[:8] &&
			appointment.Customer == credit.Customer &&
			appointment.Amount == credit.Amount &&
			appointment.Status == "ACTIVE" &&
			allowedServiceType(appointment.ServiceType) &&
			appointment.ServiceType == credit.ServiceType {
			return appointment
		}
	}
	return nil
}

func allowedServiceType(service_type string) bool {
	return service_type == "CLEAN" || service_type == "XRAY" || service_type == "SURG"
}
