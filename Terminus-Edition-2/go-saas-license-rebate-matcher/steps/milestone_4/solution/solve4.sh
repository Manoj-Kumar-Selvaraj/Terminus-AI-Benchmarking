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

type License struct {
	ID            string
	Tenant        string
	Amount        int
	Status        string
	Tier          string
	LicenseEnd    string
	HasLicenseEnd bool
	Row           int
}

type Rebate struct {
	LicenseID     string
	Tenant        string
	Amount        int
	Tier          string
	RebateDate    string
	HasRebateDate bool
}

type TierPolicy struct {
	Enabled  bool
	Priority int
	Row      int
}

type Limit struct {
	Tenant        string
	EffectiveDate string
	MaxCents      int
	Row           int
}

type Blackout struct {
	LicenseID string
	Start     string
	End       string
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
	licenses, licenseDates, err := loadLicenses("/app/data/licenses.csv")
	if err != nil {
		return err
	}
	rebates, rebateDates, err := loadRebates("/app/data/rebates.csv")
	if err != nil {
		return err
	}
	openDates, err := loadOpenDates("/app/config/cutoff_calendar.txt")
	if err != nil {
		return err
	}
	policies, err := loadTierPolicies("/app/config/tier_policy.csv")
	if err != nil {
		return err
	}
	limits, err := loadLimits("/app/config/tenant_limits.csv")
	if err != nil {
		return err
	}
	blackouts, err := loadBlackouts("/app/config/license_blackouts.csv")
	if err != nil {
		return err
	}
	return writeOutputs(licenses, rebates, openDates, policies, limits, blackouts, licenseDates || rebateDates)
}

func loadLicenses(path string) ([]License, bool, error) {
	header, rows, err := readCSV(path)
	if err != nil {
		return nil, false, err
	}
	hasDate := headerIndex(header, "license_end") >= 0
	out := make([]License, 0, len(rows))
	for i, row := range rows {
		amount, ok := parseInt(get(row, header, "amount_cents"))
		if !ok {
			return nil, hasDate, fmt.Errorf("invalid license amount on row %d", i+2)
		}
		out = append(out, License{
			ID:            clean(get(row, header, "license_id")),
			Tenant:        clean(get(row, header, "tenant_id")),
			Amount:        amount,
			Status:        strings.ToUpper(clean(get(row, header, "status"))),
			Tier:          canonicalTier(get(row, header, "tier")),
			LicenseEnd:    clean(get(row, header, "license_end")),
			HasLicenseEnd: hasDate,
			Row:           i,
		})
	}
	return out, hasDate, nil
}

func loadRebates(path string) ([]Rebate, bool, error) {
	header, rows, err := readCSV(path)
	if err != nil {
		return nil, false, err
	}
	hasDate := headerIndex(header, "rebate_date") >= 0
	out := make([]Rebate, 0, len(rows))
	for i, row := range rows {
		amount, ok := parseInt(get(row, header, "amount_cents"))
		if !ok {
			return nil, hasDate, fmt.Errorf("invalid rebate amount on row %d", i+2)
		}
		out = append(out, Rebate{
			LicenseID:     clean(get(row, header, "license_id")),
			Tenant:        clean(get(row, header, "tenant_id")),
			Amount:        amount,
			Tier:          canonicalTier(get(row, header, "tier")),
			RebateDate:    clean(get(row, header, "rebate_date")),
			HasRebateDate: hasDate,
		})
	}
	return out, hasDate, nil
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
	header := make([]string, len(rows[0]))
	for i, name := range rows[0] {
		header[i] = strings.ToLower(clean(name))
	}
	return header, rows[1:], nil
}

func writeOutputs(licenses []License, rebates []Rebate, openDates map[string]bool, policies map[string]TierPolicy, limits []Limit, blackouts []Blackout, dated bool) error {
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

	used := make([]bool, len(licenses))
	budgetUsed := map[string]int{}
	summary := Summary{}
	for _, rebate := range rebates {
		matchIndex := findMatch(licenses, rebate, used, openDates, policies, blackouts, dated)
		tier := ""
		status := "UNMATCHED"
		if matchIndex >= 0 && withinLimit(rebate, limits, budgetUsed, dated) {
			used[matchIndex] = true
			if dated {
				budgetUsed[limitKey(rebate)] += rebate.Amount
			}
			tier = licenses[matchIndex].Tier
			status = "MATCHED"
			summary.MatchedCount++
			summary.MatchedAmountCents += rebate.Amount
		} else {
			summary.UnmatchedCount++
			summary.UnmatchedAmountCents += rebate.Amount
		}
		if err := writer.Write([]string{rebate.LicenseID, rebate.Tenant, tier, strconv.Itoa(rebate.Amount), status}); err != nil {
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

func findMatch(licenses []License, rebate Rebate, used []bool, openDates map[string]bool, policies map[string]TierPolicy, blackouts []Blackout, dated bool) int {
	best := -1
	for i := range licenses {
		license := licenses[i]
		if used[i] ||
			license.ID != rebate.LicenseID ||
			license.Tenant != rebate.Tenant ||
			license.Amount != rebate.Amount ||
			license.Status != "LICENSED" ||
			!tierEnabled(license.Tier, policies) ||
			!rebateTierMatches(rebate.Tier, license.Tier) {
			continue
		}
		if dated {
			if !rebate.HasRebateDate || !license.HasLicenseEnd ||
				rebate.RebateDate == "" || license.LicenseEnd == "" ||
				!openDates[rebate.RebateDate] ||
				rebate.RebateDate > license.LicenseEnd ||
				isBlackedOut(license, blackouts) {
				continue
			}
		}
		if best < 0 || betterCandidate(license, licenses[best], rebate.Tier == "ANY", dated, policies) {
			best = i
		}
	}
	return best
}

func betterCandidate(candidate License, current License, anyTier bool, dated bool, policies map[string]TierPolicy) bool {
	if dated && candidate.LicenseEnd != current.LicenseEnd {
		return candidate.LicenseEnd > current.LicenseEnd
	}
	if anyTier {
		candidatePriority := priorityRank(candidate.Tier, policies)
		currentPriority := priorityRank(current.Tier, policies)
		if candidatePriority != currentPriority {
			return candidatePriority < currentPriority
		}
	}
	return candidate.Row < current.Row
}

func withinLimit(rebate Rebate, limits []Limit, used map[string]int, dated bool) bool {
	if !dated {
		return true
	}
	limit, ok := selectLimit(rebate, limits)
	if !ok {
		return false
	}
	return used[limitKey(rebate)]+rebate.Amount <= limit.MaxCents
}

func selectLimit(rebate Rebate, limits []Limit) (Limit, bool) {
	var selected Limit
	found := false
	for _, limit := range limits {
		if limit.Tenant != rebate.Tenant || limit.EffectiveDate == "" || limit.EffectiveDate > rebate.RebateDate {
			continue
		}
		if !found || limit.EffectiveDate > selected.EffectiveDate || (limit.EffectiveDate == selected.EffectiveDate && limit.Row > selected.Row) {
			selected = limit
			found = true
		}
	}
	return selected, found
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

func loadTierPolicies(path string) (map[string]TierPolicy, error) {
	header, rows, err := readCSV(path)
	if err != nil {
		return nil, err
	}
	policies := map[string]TierPolicy{}
	for i, row := range rows {
		tier := canonicalTier(get(row, header, "tier"))
		if tier == "" || tier == "ANY" {
			continue
		}
		priority, ok := parseInt(get(row, header, "priority"))
		if !ok {
			priority = 1_000_000 + i
		}
		policies[tier] = TierPolicy{Enabled: enabledValue(get(row, header, "enabled")), Priority: priority, Row: i}
	}
	return policies, nil
}

func loadLimits(path string) ([]Limit, error) {
	header, rows, err := readCSV(path)
	if err != nil {
		return nil, err
	}
	limits := []Limit{}
	for i, row := range rows {
		amount, ok := parseInt(get(row, header, "max_daily_amount_cents"))
		if !ok {
			continue
		}
		limits = append(limits, Limit{
			Tenant:        clean(get(row, header, "tenant_id")),
			EffectiveDate: clean(get(row, header, "effective_date")),
			MaxCents:      amount,
			Row:           i,
		})
	}
	return limits, nil
}

func loadBlackouts(path string) ([]Blackout, error) {
	header, rows, err := readCSV(path)
	if err != nil {
		return nil, err
	}
	blackouts := []Blackout{}
	for _, row := range rows {
		blackout := Blackout{
			LicenseID: clean(get(row, header, "license_id")),
			Start:     clean(get(row, header, "start_date")),
			End:       clean(get(row, header, "end_date")),
		}
		if blackout.LicenseID == "" || blackout.Start == "" || blackout.End == "" || blackout.Start > blackout.End {
			continue
		}
		blackouts = append(blackouts, blackout)
	}
	return blackouts, nil
}

func isBlackedOut(license License, blackouts []Blackout) bool {
	for _, blackout := range blackouts {
		if blackout.LicenseID == license.ID && license.LicenseEnd >= blackout.Start && license.LicenseEnd <= blackout.End {
			return true
		}
	}
	return false
}

func rebateTierMatches(rebateTier string, licenseTier string) bool {
	return rebateTier == "ANY" || rebateTier == licenseTier
}

func tierEnabled(tier string, policies map[string]TierPolicy) bool {
	policy, ok := policies[tier]
	return ok && policy.Enabled
}

func priorityRank(tier string, policies map[string]TierPolicy) int {
	if policy, ok := policies[tier]; ok {
		return policy.Priority
	}
	return 1_000_000
}

func enabledValue(value string) bool {
	switch strings.ToLower(clean(value)) {
	case "true", "1", "yes", "y", "enabled":
		return true
	default:
		return false
	}
}

func canonicalTier(value string) string {
	switch strings.ToUpper(clean(value)) {
	case "STR":
		return "STARTER"
	case "BUS":
		return "BUSINESS"
	case "ENT":
		return "ENTERPRISE"
	case "STARTER", "BUSINESS", "ENTERPRISE", "ANY":
		return strings.ToUpper(clean(value))
	default:
		return strings.ToUpper(clean(value))
	}
}

func limitKey(rebate Rebate) string {
	return rebate.Tenant + "|" + rebate.RebateDate
}

func get(row []string, header []string, name string) string {
	index := headerIndex(header, name)
	if index < 0 || index >= len(row) {
		return ""
	}
	return row[index]
}

func headerIndex(header []string, name string) int {
	for i, field := range header {
		if field == name {
			return i
		}
	}
	return -1
}

func parseInt(value string) (int, bool) {
	number, err := strconv.Atoi(clean(value))
	return number, err == nil
}

func clean(value string) string {
	return strings.TrimSpace(value)
}
GO

/app/scripts/run_batch.sh
test -s /app/out/rebate_report.csv
test -s /app/out/rebate_summary.json
