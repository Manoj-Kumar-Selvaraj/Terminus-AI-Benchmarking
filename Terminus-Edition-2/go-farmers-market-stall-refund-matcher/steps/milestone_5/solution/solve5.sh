#!/usr/bin/env bash
set -euo pipefail

cd /app

if grep -q 'func marketCalendarOK' /app/cmd/reconcile/main.go; then
  /app/scripts/run_batch.sh
  test -s /app/out/refund_report.csv
  test -s /app/out/refund_summary.json
  exit 0
fi

cat > /app/cmd/reconcile/main.go <<'GO'
package main

import (
	"encoding/csv"
	"encoding/json"
	"os"
	"path/filepath"
	"sort"
	"strconv"
	"strings"
)

type stall struct {
	id, customer, amount, status, stallType, marketDate string
	row                                                  int
	used                                                 bool
}

type refund struct {
	id, stallID, customer, amount, stallType, refundDate string
}

type policy struct {
	enabled  bool
	priority int
}

func clean(s string) string  { return strings.TrimSpace(s) }
func upper(s string) string { return strings.ToUpper(clean(s)) }

func canonStallType(raw string) string {
	switch upper(raw) {
	case "PRD", "PRODUCE":
		return "PRODUCE"
	case "CRT", "CRAFT":
		return "CRAFT"
	case "FOD", "FOOD":
		return "FOOD"
	case "ANY":
		return "ANY"
	default:
		return upper(raw)
	}
}

func stallTypeOK(value string) bool {
	return value == "PRODUCE" || value == "CRAFT" || value == "FOOD"
}

func readCSV(path string) []map[string]string {
	file, err := os.Open(path)
	if err != nil {
		return nil
	}
	defer file.Close()
	reader := csv.NewReader(file)
	rows, err := reader.ReadAll()
	if err != nil || len(rows) == 0 {
		return nil
	}
	headers := rows[0]
	out := []map[string]string{}
	for _, row := range rows[1:] {
		record := map[string]string{}
		for i, key := range headers {
			if i < len(row) {
				record[clean(key)] = clean(row[i])
			}
		}
		out = append(out, record)
	}
	return out
}

func loadOpenRefundDates() map[string]bool {
	out := map[string]bool{}
	data, err := os.ReadFile("/app/config/cutoff_calendar.txt")
	if err != nil {
		return out
	}
	for _, line := range strings.Split(string(data), "\n") {
		fields := strings.Fields(line)
		if len(fields) >= 2 && strings.EqualFold(fields[1], "open") {
			out[fields[0]] = true
		}
	}
	return out
}

func loadMarketCalendar() map[string]bool {
	out := map[string]bool{}
	data, err := os.ReadFile("/app/config/market_calendar.txt")
	if err != nil {
		return out
	}
	for _, line := range strings.Split(string(data), "\n") {
		fields := strings.Fields(line)
		if len(fields) >= 2 && strings.EqualFold(fields[1], "OPEN") {
			out[fields[0]] = true
		}
	}
	return out
}

func loadPolicies() map[string]policy {
	defaults := map[string]policy{
		"PRODUCE": {true, 2},
		"CRAFT":   {true, 1},
		"FOOD":    {true, 3},
	}
	for _, row := range readCSV("/app/config/stall_policy.csv") {
		stallType := canonStallType(row["stall_type"])
		priority, err := strconv.Atoi(clean(row["priority"]))
		if err != nil {
			priority = 999
		}
		defaults[stallType] = policy{upper(row["enabled"]) == "Y", priority}
	}
	return defaults
}

func dateMode(stalls []stall, refunds []refund) bool {
	for _, s := range stalls {
		if s.marketDate != "" {
			return true
		}
	}
	for _, r := range refunds {
		if r.refundDate != "" {
			return true
		}
	}
	return false
}

func dateOK(src stall, act refund, openDates map[string]bool, dated bool) bool {
	if !dated {
		return true
	}
	if src.marketDate == "" && act.refundDate == "" {
		return true
	}
	if src.marketDate == "" || act.refundDate == "" {
		return false
	}
	if !openDates[act.refundDate] {
		return false
	}
	return true
}

func marketCalendarOK(src stall, act refund, cal map[string]bool, dated bool) bool {
	if !dated {
		return true
	}
	if src.marketDate == "" && act.refundDate == "" {
		return true
	}
	if src.marketDate == "" || act.refundDate == "" {
		return false
	}
	if act.refundDate < src.marketDate {
		return false
	}
	if !cal[src.marketDate] || !cal[act.refundDate] {
		return false
	}
	openDays := 0
	for day := range cal {
		if day > src.marketDate && day <= act.refundDate {
			openDays++
		}
	}
	return openDays <= 2
}

func main() {
	stalls := []stall{}
	for i, row := range readCSV("/app/data/stalls.csv") {
		stalls = append(stalls, stall{
			clean(row["stall_id"]),
			clean(row["vendor_id"]),
			clean(row["amount_cents"]),
			upper(row["status"]),
			canonStallType(row["stall_type"]),
			clean(row["market_date"]),
			i,
			false,
		})
	}
	refunds := []refund{}
	for _, row := range readCSV("/app/data/refunds.csv") {
		refunds = append(refunds, refund{
			clean(row["settlement_id"]),
			clean(row["stall_id"]),
			clean(row["vendor_id"]),
			clean(row["amount_cents"]),
			canonStallType(row["stall_type"]),
			clean(row["refund_date"]),
		})
	}
	openDates := loadOpenRefundDates()
	marketCal := loadMarketCalendar()
	policies := loadPolicies()
	dated := dateMode(stalls, refunds)

	os.MkdirAll("/app/out", 0o755)
	report, _ := os.Create("/app/out/refund_report.csv")
	defer report.Close()
	writer := csv.NewWriter(report)
	defer writer.Flush()
	writer.Write([]string{"stall_id", "vendor_id", "stall_type", "amount_cents", "status"})

	mc, uc, ma, ua := 0, 0, 0, 0
	for _, act := range refunds {
		candidates := []int{}
		for i, src := range stalls {
			pol := policies[src.stallType]
			typeMatches := src.stallType == act.stallType || act.stallType == "ANY"
			if !src.used && src.id == act.stallID && src.customer == act.customer && src.amount == act.amount &&
				src.status == "RESERVED" && stallTypeOK(src.stallType) && typeMatches && pol.enabled &&
				dateOK(src, act, openDates, dated) && marketCalendarOK(src, act, marketCal, dated) {
				candidates = append(candidates, i)
			}
		}
		sort.SliceStable(candidates, func(a, b int) bool {
			left, right := stalls[candidates[a]], stalls[candidates[b]]
			if dated && left.marketDate != right.marketDate {
				return left.marketDate > right.marketDate
			}
			if policies[left.stallType].priority != policies[right.stallType].priority {
				return policies[left.stallType].priority < policies[right.stallType].priority
			}
			return left.row < right.row
		})
		amt, _ := strconv.Atoi(act.amount)
		if len(candidates) > 0 {
			best := candidates[0]
			stalls[best].used = true
			mc++
			ma += amt
			reportType := act.stallType
			if act.stallType == "ANY" {
				reportType = stalls[best].stallType
			}
			writer.Write([]string{act.stallID, act.customer, reportType, act.amount, "MATCHED"})
		} else {
			uc++
			ua += amt
			writer.Write([]string{act.stallID, act.customer, "", act.amount, "UNMATCHED"})
		}
	}

	summary, _ := json.MarshalIndent(map[string]int{
		"matched_count":          mc,
		"matched_amount_cents":   ma,
		"unmatched_count":        uc,
		"unmatched_amount_cents": ua,
	}, "", "  ")
	os.WriteFile(filepath.Clean("/app/out/refund_summary.json"), append(summary, '\n'), 0o644)
}
GO
/app/scripts/run_batch.sh
test -s /app/out/refund_report.csv
test -s /app/out/refund_summary.json
