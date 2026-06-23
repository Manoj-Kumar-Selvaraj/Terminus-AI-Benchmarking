package main

import (
	"encoding/csv"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strconv"
)

type License struct {
	ID       string
	Tenant string
	Amount   int
	Status   string
	Tier   string
}

type Rebate struct {
	LicenseID string
	Tenant  string
	Amount    int
	Tier    string
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
	licenses, err := loadLicenses("/app/data/licenses.csv")
	if err != nil {
		return err
	}
	rebates, err := loadRebates("/app/data/rebates.csv")
	if err != nil {
		return err
	}
	return writeOutputs(licenses, rebates)
}

func loadLicenses(path string) ([]License, error) {
	rows, err := readRows(path)
	if err != nil {
		return nil, err
	}
	out := make([]License, 0, len(rows))
	for _, row := range rows {
		amount, err := strconv.Atoi(row[2])
		if err != nil {
			return nil, err
		}
		out = append(out, License{ID: row[0], Tenant: row[1], Amount: amount, Status: row[3], Tier: row[4]})
	}
	return out, nil
}

func loadRebates(path string) ([]Rebate, error) {
	rows, err := readRows(path)
	if err != nil {
		return nil, err
	}
	out := make([]Rebate, 0, len(rows))
	for _, row := range rows {
		amount, err := strconv.Atoi(row[2])
		if err != nil {
			return nil, err
		}
		out = append(out, Rebate{LicenseID: row[0], Tenant: row[1], Amount: amount, Tier: row[3]})
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

func writeOutputs(licenses []License, rebates []Rebate) error {
	if err := os.MkdirAll("/app/out", 0o755); err != nil {
		return err
	}
	reportPath := filepath.Join("/app/out", "rebate_report.csv")
	reportFile, err := os.Create(reportPath)
	if err != nil {
		return err
	}
	defer reportFile.Close()
	writer := csv.NewWriter(reportFile)
	defer writer.Flush()
	if err := writer.Write([]string{"license_id", "tenant_id", "tier", "amount_cents", "status"}); err != nil {
		return err
	}

	summary := Summary{}
	for _, rebate := range rebates {
		match := findMatch(licenses, rebate)
		tier := ""
		status := "UNMATCHED"
		if match != nil {
			tier = match.Tier
			status = "MATCHED"
			summary.MatchedCount++
			summary.MatchedAmountCents -= rebate.Amount
		} else {
			summary.UnmatchedCount++
			summary.UnmatchedAmountCents += rebate.Amount
		}
		if err := writer.Write([]string{
			rebate.LicenseID,
			rebate.Tenant,
			tier,
			strconv.Itoa(rebate.Amount),
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
	return os.WriteFile("/app/out/rebate_summary.json", append(summaryBytes, '\n'), 0o644)
}

func findMatch(licenses []License, rebate Rebate) *License {
	for i := range licenses {
		license := &licenses[i]
		if len(license.ID) >= 8 && len(rebate.LicenseID) >= 8 &&
			license.ID[:8] == rebate.LicenseID[:8] &&
			license.Tenant == rebate.Tenant &&
			license.Amount == rebate.Amount &&
			license.Status == "LICENSED" &&
			allowedTier(license.Tier) &&
			license.Tier == rebate.Tier {
			return license
		}
	}
	return nil
}

func allowedTier(tier string) bool {
	return tier == "STARTER" || tier == "BUSINESS" || tier == "ENTERPRISE"
}
