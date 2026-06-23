#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# This milestone solution is intentionally incremental: it applies the previous milestone first, then replaces the reconciler with the next general implementation.

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
    "time"
)

const enableAliases = true
const enableDates = false
const enableMethods = false
const enableLimits = false

type Trip struct {
    ID       string
    Customer string
    Amount   int
    Status   string
    PassType string
    WashDate string
}

type Credit struct {
    TripID     string
    Customer   string
    Amount     int
    PassType   string
    CreditDate string
}

type Summary struct {
    MatchedCount         int `json:"matched_count"`
    MatchedAmountCents   int `json:"matched_amount_cents"`
    UnmatchedCount       int `json:"unmatched_count"`
    UnmatchedAmountCents int `json:"unmatched_amount_cents"`
}

type MethodPolicy map[string]bool

type LimitPolicy struct {
    Enabled bool
    Max     int
}

func main() {
    if err := run(); err != nil {
        fmt.Fprintln(os.Stderr, err)
        os.Exit(1)
    }
}

func run() error {
    trips, tripHasDate, err := loadTrips("/app/data/washes.csv")
    if err != nil {
        return err
    }
    credits, creditHasDate, err := loadCredits("/app/data/rebates.csv")
    if err != nil {
        return err
    }

    useDates := enableDates && (tripHasDate || creditHasDate)
    openDates := map[string]bool{}
    if useDates {
        openDates, err = loadOpenDates("/app/config/cutoff_calendar.txt")
        if err != nil {
            return err
        }
    }

    methods := MethodPolicy{}
    if enableMethods {
        methods, err = loadMethods("/app/config/methods.csv")
        if err != nil {
            return err
        }
    }

    limitsMap := map[string]LimitPolicy{}
    if enableLimits {
        limitsMap, err = loadCustomerLimits("/app/config/customer_limits.csv")
        if err != nil {
            return err
        }
    }

    return writeOutputs(trips, credits, useDates, openDates, methods, limitsMap)
}

func loadTrips(path string) ([]Trip, bool, error) {
    rows, header, err := readCSV(path)
    if err != nil {
        return nil, false, err
    }
    hasDate := hasColumn(header, "wash_date")
    out := make([]Trip, 0, len(rows))
    for _, row := range rows {
        amount, err := strconv.Atoi(clean(value(row, header, "amount_cents")))
        if err != nil {
            return nil, false, err
        }
        out = append(out, Trip{
            ID:       clean(value(row, header, "wash_id")),
            Customer: clean(value(row, header, "customer_id")),
            Amount:   amount,
            Status:   strings.ToUpper(clean(value(row, header, "status"))),
            PassType: canonicalPassType(value(row, header, "plan_tier")),
            WashDate: clean(value(row, header, "wash_date")),
        })
    }
    return out, hasDate, nil
}

func loadCredits(path string) ([]Credit, bool, error) {
    rows, header, err := readCSV(path)
    if err != nil {
        return nil, false, err
    }
    hasDate := hasColumn(header, "rebate_date")
    out := make([]Credit, 0, len(rows))
    for _, row := range rows {
        amount, err := strconv.Atoi(clean(value(row, header, "amount_cents")))
        if err != nil {
            return nil, false, err
        }
        out = append(out, Credit{
            TripID:     clean(value(row, header, "wash_id")),
            Customer:   clean(value(row, header, "customer_id")),
            Amount:     amount,
            PassType:   canonicalPassType(value(row, header, "plan_tier")),
            CreditDate: clean(value(row, header, "rebate_date")),
        })
    }
    return out, hasDate, nil
}

func readCSV(path string) ([][]string, map[string]int, error) {
    f, err := os.Open(path)
    if err != nil {
        return nil, nil, err
    }
    defer f.Close()
    reader := csv.NewReader(f)
    reader.FieldsPerRecord = -1
    records, err := reader.ReadAll()
    if err != nil {
        return nil, nil, err
    }
    header := map[string]int{}
    if len(records) == 0 {
        return nil, header, nil
    }
    for idx, name := range records[0] {
        header[strings.ToLower(clean(name))] = idx
    }
    return records[1:], header, nil
}

func value(row []string, header map[string]int, name string) string {
    idx, ok := header[strings.ToLower(name)]
    if !ok || idx < 0 || idx >= len(row) {
        return ""
    }
    return row[idx]
}

func hasColumn(header map[string]int, name string) bool {
    _, ok := header[strings.ToLower(name)]
    return ok
}

func writeOutputs(trips []Trip, credits []Credit, useDates bool, openDates map[string]bool, methods MethodPolicy, limitsMap map[string]LimitPolicy) error {
    if err := os.MkdirAll("/app/out", 0o755); err != nil {
        return err
    }
    reportPath := filepath.Join("/app/out", "wash_rebate_report.csv")
    reportFile, err := os.Create(reportPath)
    if err != nil {
        return err
    }
    defer reportFile.Close()

    writer := csv.NewWriter(reportFile)
    if err := writer.Write([]string{"wash_id", "customer_id", "plan_tier", "amount_cents", "status"}); err != nil {
        return err
    }

    summary := Summary{}
    used := make([]bool, len(trips))
    for _, credit := range credits {
        matchIndex := findMatch(trips, credit, used, useDates, openDates, methods, limitsMap)
        reportTier := ""
        status := "UNMATCHED"
        if matchIndex >= 0 {
            used[matchIndex] = true
            reportTier = credit.PassType
            status = "MATCHED"
            summary.MatchedCount++
            summary.MatchedAmountCents += credit.Amount
        } else {
            summary.UnmatchedCount++
            summary.UnmatchedAmountCents += credit.Amount
        }
        if err := writer.Write([]string{
            credit.TripID,
            credit.Customer,
            reportTier,
            strconv.Itoa(credit.Amount),
            status,
        }); err != nil {
            return err
        }
    }
    writer.Flush()
    if err := writer.Error(); err != nil {
        return err
    }
    summaryBytes, err := json.MarshalIndent(summary, "", "  ")
    if err != nil {
        return err
    }
    return os.WriteFile("/app/out/wash_rebate_summary.json", append(summaryBytes, '\n'), 0o644)
}

func findMatch(trips []Trip, credit Credit, used []bool, useDates bool, openDates map[string]bool, methods MethodPolicy, limitsMap map[string]LimitPolicy) int {
    best := -1
    for i := range trips {
        if used[i] {
            continue
        }
        trip := trips[i]
        if !baseEligible(trip, credit) {
            continue
        }
        if enableMethods && !methods[credit.PassType] {
            continue
        }
        if enableLimits && !limitEligible(limitsMap, credit) {
            continue
        }
        if useDates && !dateEligible(trip.WashDate, credit.CreditDate, openDates) {
            continue
        }
        if best < 0 || !useDates || trip.WashDate > trips[best].WashDate || (trip.WashDate == trips[best].WashDate && i < best) {
            best = i
        }
    }
    return best
}

func baseEligible(trip Trip, credit Credit) bool {
    return trip.ID == credit.TripID &&
        trip.Customer == credit.Customer &&
        trip.Amount == credit.Amount &&
        trip.Status == "COMPLETED" &&
        allowedPassType(trip.PassType) &&
        allowedPassType(credit.PassType) &&
        trip.PassType == credit.PassType
}

func dateEligible(washDate string, rebateDate string, openDates map[string]bool) bool {
    if rebateDate == "" || washDate == "" || !openDates[rebateDate] {
        return false
    }
    rebateParsed, err := time.Parse("2006-01-02", rebateDate)
    if err != nil {
        return false
    }
    washParsed, err := time.Parse("2006-01-02", washDate)
    if err != nil {
        return false
    }
    return !rebateParsed.After(washParsed)
}

func loadOpenDates(path string) (map[string]bool, error) {
    data, err := os.ReadFile(path)
    if err != nil {
        return nil, err
    }
    out := map[string]bool{}
    for _, line := range strings.Split(string(data), "\n") {
        fields := strings.Fields(line)
        if len(fields) >= 2 && strings.EqualFold(fields[1], "open") {
            if _, err := time.Parse("2006-01-02", fields[0]); err == nil {
                out[fields[0]] = true
            }
        }
    }
    return out, nil
}

func loadMethods(path string) (MethodPolicy, error) {
    rows, header, err := readCSV(path)
    if err != nil {
        return nil, err
    }
    out := MethodPolicy{}
    for _, row := range rows {
        tier := canonicalPassType(value(row, header, "plan_tier"))
        if !allowedPassType(tier) {
            continue
        }
        out[tier] = strings.EqualFold(clean(value(row, header, "rebate_enabled")), "true")
    }
    return out, nil
}

func loadCustomerLimits(path string) (map[string]LimitPolicy, error) {
    rows, header, err := readCSV(path)
    if err != nil {
        return nil, err
    }
    out := map[string]LimitPolicy{}
    for _, row := range rows {
        customer := clean(value(row, header, "customer_id"))
        tier := canonicalPassType(value(row, header, "plan_tier"))
        if customer == "" || !allowedPassType(tier) {
            continue
        }
        key := limitKey(customer, tier)
        maxText := clean(value(row, header, "max_rebate_cents"))
        max, err := strconv.Atoi(maxText)
        enabledText := clean(value(row, header, "enabled"))
        if err != nil || max < 0 || enabledText == "" {
            out[key] = LimitPolicy{Enabled: false}
            continue
        }
        out[key] = LimitPolicy{Enabled: strings.EqualFold(enabledText, "true"), Max: max}
    }
    return out, nil
}

func limitEligible(limitsMap map[string]LimitPolicy, credit Credit) bool {
    policy, ok := limitsMap[limitKey(credit.Customer, credit.PassType)]
    return ok && policy.Enabled && credit.Amount <= policy.Max
}

func limitKey(customer string, tier string) string {
    return clean(customer) + " " + canonicalPassType(tier)
}

func clean(value string) string {
    return strings.TrimSpace(value)
}

func canonicalPassType(passType string) string {
    normalized := strings.ToUpper(clean(passType))
    if enableAliases {
        switch normalized {
        case "BS":
            return "BASIC"
        case "PL":
            return "PLUS"
        case "PR":
            return "PRO"
        }
    }
    return normalized
}

func allowedPassType(passType string) bool {
    switch canonicalPassType(passType) {
    case "BASIC", "PLUS", "PRO":
        return true
    default:
        return false
    }
}

GO

/app/scripts/run_batch.sh
test -s /app/out/wash_rebate_report.csv
test -s /app/out/wash_rebate_summary.json
