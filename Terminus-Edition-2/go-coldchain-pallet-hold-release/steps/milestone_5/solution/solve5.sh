#!/bin/bash
set -euo pipefail

cd /app

# Sequential oracle runs may already have produced a calendar-capable program.
# In that case, validate the existing code instead of rewriting it again.
if grep -q 'func calendarOK' /app/cmd/reconcile/main.go; then
  /app/scripts/run_batch.sh
  test -s /app/out/pallet_release_report.csv
  test -s /app/out/pallet_release_summary.txt
  exit 0
fi

cat > /app/cmd/reconcile/main.go <<'GO'
package main

import (
	"encoding/csv"
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"strconv"
	"strings"
)

type hold struct {
	id, pallet, zone, band, amount, holdTS, status, bay string
	row                                                  int
	used                                                 bool
}

type release struct {
	id, holdID, pallet, zone, band, amount, releaseTS, reason, bay string
}

type window struct{ zone, open, close, state string }
type policy struct {
	enabled  bool
	priority int
}

func clean(s string) string { return strings.TrimSpace(s) }
func upper(s string) string { return strings.ToUpper(clean(s)) }
func digits(s string) bool {
	if len(s) != 14 {
		return false
	}
	for _, r := range s {
		if r < '0' || r > '9' {
			return false
		}
	}
	return true
}
func canon(s string) string {
	switch upper(s) {
	case "IN", "FROZEN":
		return "FROZEN"
	case "CU", "CHILL":
		return "CHILL"
	case "SE", "AMBIENT":
		return "AMBIENT"
	case "ANY":
		return "ANY"
	default:
		return upper(s)
	}
}
func bandOK(s string) bool { return s == "FROZEN" || s == "CHILL" || s == "AMBIENT" }
func reasonOK(s string) bool { return s == "SPOIL" || s == "QUAR" || s == "OVERRIDE" }

func readCSV(path string) []map[string]string {
	f, err := os.Open(path)
	if err != nil {
		return nil
	}
	defer f.Close()
	reader := csv.NewReader(f)
	rows, err := reader.ReadAll()
	if err != nil || len(rows) == 0 {
		return nil
	}
	headers := rows[0]
	out := []map[string]string{}
	for _, row := range rows[1:] {
		m := map[string]string{}
		for i, h := range headers {
			if i < len(row) {
				m[clean(h)] = clean(row[i])
			}
		}
		out = append(out, m)
	}
	return out
}

func loadPolicies() map[string]policy {
	policies := map[string]policy{"FROZEN": {true, 2}, "CHILL": {true, 1}, "AMBIENT": {true, 3}}
	for _, row := range readCSV("/app/config/band_policy.csv") {
		band := canon(row["temp_band"])
		priority, err := strconv.Atoi(clean(row["priority"]))
		if err != nil {
			priority = 999
		}
		policies[band] = policy{upper(row["enabled"]) == "Y", priority}
	}
	return policies
}

func loadCalendar() map[string]bool {
	out := map[string]bool{}
	data, err := os.ReadFile("/app/config/release_calendar.txt")
	if err != nil {
		return out
	}
	for _, line := range strings.Split(string(data), "\n") {
		fields := strings.Fields(line)
		if len(fields) >= 2 && len(fields[0]) == 8 && upper(fields[1]) == "OPEN" {
			out[fields[0]] = true
		}
	}
	return out
}

func windowOK(src hold, act release, windows []window) bool {
	if !digits(src.holdTS) || !digits(act.releaseTS) || act.releaseTS < src.holdTS {
		return false
	}
	for _, w := range windows {
		if w.zone == src.zone && upper(w.state) == "OPEN" && digits(w.open) && digits(w.close) &&
			src.holdTS >= w.open && src.holdTS <= w.close && act.releaseTS <= w.close {
			return true
		}
	}
	return false
}

func calendarOK(src hold, act release, cal map[string]bool) bool {
	if !digits(src.holdTS) || !digits(act.releaseTS) || act.releaseTS < src.holdTS {
		return false
	}
	holdDate, releaseDate := src.holdTS[:8], act.releaseTS[:8]
	if !cal[holdDate] || !cal[releaseDate] {
		return false
	}
	openDays := 0
	for day := range cal {
		if day > holdDate && day <= releaseDate {
			openDays++
		}
	}
	return openDays <= 2
}

func main() {
	holds := []hold{}
	for i, row := range readCSV("/app/data/holds.csv") {
		holds = append(holds, hold{clean(row["hold_id"]), clean(row["pallet_id"]), clean(row["zone_id"]), canon(row["temp_band"]), clean(row["amount"]), clean(row["hold_ts"]), upper(row["status"]), clean(row["bay"]), i, false})
	}
	releases := []release{}
	for _, row := range readCSV("/app/data/releases.csv") {
		releases = append(releases, release{clean(row["release_id"]), clean(row["hold_id"]), clean(row["pallet_id"]), clean(row["zone_id"]), canon(row["temp_band"]), clean(row["amount"]), clean(row["release_ts"]), upper(row["reason"]), clean(row["bay"])})
	}
	windows := []window{}
	for _, row := range readCSV("/app/config/windows.csv") {
		windows = append(windows, window{clean(row["zone_id"]), clean(row["open_ts"]), clean(row["close_ts"]), upper(row["state"])})
	}
	policies := loadPolicies()
	calendar := loadCalendar()

	os.MkdirAll("/app/out", 0755)
	report, _ := os.Create("/app/out/pallet_release_report.csv")
	defer report.Close()
	writer := csv.NewWriter(report)
	defer writer.Flush()
	writer.Write([]string{"release_id", "hold_id", "pallet_id", "zone_id", "temp_band", "amount", "reason", "status"})
	mc, uc, ma, ua := 0, 0, 0, 0
	for _, act := range releases {
		candidates := []int{}
		for i, src := range holds {
			pol := policies[src.band]
			bandMatches := src.band == act.band || act.band == "ANY"
			if !src.used && src.id == act.holdID && src.pallet == act.pallet && src.zone == act.zone && src.bay == act.bay &&
				src.amount == act.amount && src.status == "QUARANTINED" && reasonOK(act.reason) &&
				bandOK(src.band) && bandMatches && pol.enabled && windowOK(src, act, windows) && calendarOK(src, act, calendar) {
				candidates = append(candidates, i)
			}
		}
		sort.SliceStable(candidates, func(a, b int) bool {
			left, right := holds[candidates[a]], holds[candidates[b]]
			if left.holdTS != right.holdTS {
				return left.holdTS > right.holdTS
			}
			if policies[left.band].priority != policies[right.band].priority {
				return policies[left.band].priority < policies[right.band].priority
			}
			return left.row < right.row
		})
		amt, _ := strconv.Atoi(act.amount)
		if len(candidates) > 0 {
			best := candidates[0]
			holds[best].used = true
			mc++
			ma += amt
			writer.Write([]string{act.id, act.holdID, act.pallet, act.zone, holds[best].band, act.amount, act.reason, "MATCHED"})
		} else {
			uc++
			ua += amt
			writer.Write([]string{act.id, act.holdID, act.pallet, act.zone, "", act.amount, act.reason, "UNMATCHED"})
		}
	}
	os.WriteFile(filepath.Clean("/app/out/pallet_release_summary.txt"), []byte(fmt.Sprintf("matched_count=%d\nmatched_amount=%d\nunmatched_count=%d\nunmatched_amount=%d\n", mc, ma, uc, ua)), 0644)
}
GO
/app/scripts/run_batch.sh
