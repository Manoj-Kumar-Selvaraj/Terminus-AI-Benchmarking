#!/usr/bin/env bash
set -euo pipefail
# Milestone 1 oracle implements only base matching gates from milestone 1 instructions.

cd /app

cat > /app/cmd/reconcile/main.go <<'GO'
package main

import (
	"encoding/csv"
	"encoding/json"
	"os"
	"strconv"
	"strings"
)

type Pass struct{ ID, Guest, Status, Access string; Amount int }
type Refund struct{ PassID, Guest, Access string; Amount int }
type Summary struct {
	MatchedCount         int `json:"matched_count"`
	MatchedAmountCents   int `json:"matched_amount_cents"`
	UnmatchedCount       int `json:"unmatched_count"`
	UnmatchedAmountCents int `json:"unmatched_amount_cents"`
}

func main() {
	if err := run(); err != nil {
		panic(err)
	}
}

func run() error {
	passRows, err := readTable("/app/data/passes.csv")
	if err != nil {
		return err
	}
	refundRows, err := readTable("/app/data/refunds.csv")
	if err != nil {
		return err
	}
	passes := loadPasses(passRows)
	refunds := loadRefunds(refundRows)
	return writeOutputs(passes, refunds)
}

func readTable(path string) ([]map[string]string, error) {
	f, err := os.Open(path)
	if err != nil {
		return nil, err
	}
	defer f.Close()
	r := csv.NewReader(f)
	r.FieldsPerRecord = -1
	rows, err := r.ReadAll()
	if err != nil {
		return nil, err
	}
	if len(rows) == 0 {
		return nil, nil
	}
	headers := rows[0]
	out := []map[string]string{}
	for _, vals := range rows[1:] {
		m := map[string]string{}
		for i, h := range headers {
			v := ""
			if i < len(vals) {
				v = vals[i]
			}
			m[clean(h)] = v
		}
		out = append(out, m)
	}
	return out, nil
}

func loadPasses(rows []map[string]string) []Pass {
	out := []Pass{}
	for _, row := range rows {
		amount, err := strconv.Atoi(clean(row["amount_cents"]))
		if err != nil {
			continue
		}
		out = append(out, Pass{
			ID: clean(row["pass_id"]), Guest: clean(row["guest_id"]), Amount: amount,
			Status: clean(row["status"]), Access: canon(clean(row["access_type"])),
		})
	}
	return out
}

func loadRefunds(rows []map[string]string) []Refund {
	out := []Refund{}
	for _, row := range rows {
		amount, err := strconv.Atoi(clean(row["amount_cents"]))
		if err != nil {
			continue
		}
		out = append(out, Refund{
			PassID: clean(row["pass_id"]), Guest: clean(row["guest_id"]), Amount: amount,
			Access: canon(clean(row["access_type"])),
		})
	}
	return out
}

func writeOutputs(passes []Pass, refunds []Refund) error {
	if err := os.MkdirAll("/app/out", 0o755); err != nil {
		return err
	}
	report, err := os.Create("/app/out/refund_report.csv")
	if err != nil {
		return err
	}
	defer report.Close()
	w := csv.NewWriter(report)
	if err := w.Write([]string{"pass_id", "guest_id", "access_type", "amount_cents", "status"}); err != nil {
		return err
	}
	used := make([]bool, len(passes))
	summary := Summary{}
	for _, refund := range refunds {
		idx := findMatch(passes, refund, used)
		access := ""
		status := "UNMATCHED"
		if idx >= 0 {
			used[idx] = true
			access = passes[idx].Access
			status = "MATCHED"
			summary.MatchedCount++
			summary.MatchedAmountCents += refund.Amount
		} else {
			summary.UnmatchedCount++
			summary.UnmatchedAmountCents += refund.Amount
		}
		if err := w.Write([]string{refund.PassID, refund.Guest, access, strconv.Itoa(refund.Amount), status}); err != nil {
			return err
		}
	}
	w.Flush()
	if err := w.Error(); err != nil {
		return err
	}
	body, err := json.MarshalIndent(summary, "", "  ")
	if err != nil {
		return err
	}
	return os.WriteFile("/app/out/refund_summary.json", append(body, '\n'), 0o644)
}

func findMatch(passes []Pass, refund Refund, used []bool) int {
	for i, pass := range passes {
		if used[i] || !eligible(pass, refund) {
			continue
		}
		return i
	}
	return -1
}

func eligible(pass Pass, refund Refund) bool {
	return pass.ID == refund.PassID && pass.Guest == refund.Guest && pass.Amount == refund.Amount &&
		strings.EqualFold(pass.Status, "ACTIVE") && allowed(pass.Access) && pass.Access == refund.Access
}

func clean(v string) string { return strings.TrimSpace(v) }
func canon(v string) string { return strings.ToUpper(clean(v)) }
func allowed(v string) bool { v = canon(v); return v == "DAY" || v == "SEASON" || v == "VIP" }
GO

/app/scripts/run_batch.sh
test -s /app/out/refund_report.csv
test -s /app/out/refund_summary.json
