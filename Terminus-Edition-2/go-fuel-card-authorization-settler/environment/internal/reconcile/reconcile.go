package reconcile

import (
	"encoding/csv"
	"fmt"
	"os"
	"path/filepath"
	"strconv"
	"strings"
)

const milestoneLevel = 0

type sourceRow struct {
	authID, fleetID, batchID, kind, amount, sourceTS, status, location string
	used bool
}

type actionRow struct {
	actionID, authID, fleetID, batchID, kind, amount, actionTS, reason, location string
}

func readCSV(path string) []map[string]string {
	f, err := os.Open(path)
	if err != nil {
		panic(err)
	}
	defer f.Close()
	r := csv.NewReader(f)
	r.FieldsPerRecord = -1
	rows, err := r.ReadAll()
	if err != nil {
		panic(err)
	}
	if len(rows) == 0 {
		return nil
	}
	headers := rows[0]
	out := []map[string]string{}
	for _, row := range rows[1:] {
		m := map[string]string{}
		for i, h := range headers {
			if i < len(row) {
				m[strings.TrimSpace(h)] = strings.TrimSpace(row[i])
			}
		}
		out = append(out, m)
	}
	return out
}

func canonKind(s string) string {
	s = strings.ToUpper(strings.TrimSpace(s))
	switch s {
	case "DSL":
		return "DIESEL"
	case "PETROL":
		return "GAS"
	case "CHARGE":
		return "EV"
	default:
		return s
	}
}

// Run intentionally contains several realistic reconciliation defects for agents to repair.
func Run() error {
	sources := []sourceRow{}
	for _, m := range readCSV("/app/data/authorizations.csv") {
		sources = append(sources, sourceRow{m["auth_id"], m["fleet_id"], m["batch_id"], canonKind(m["kind"]), m["amount"], m["source_ts"], m["status"], m["location"], false})
	}
	actions := []actionRow{}
	for _, m := range readCSV("/app/data/reversals.csv") {
		actions = append(actions, actionRow{m["action_id"], m["auth_id"], m["fleet_id"], m["batch_id"], canonKind(m["kind"]), m["amount"], m["action_ts"], m["reason"], m["location"]})
	}
	if err := os.MkdirAll("/app/out", 0o755); err != nil { return err }
	f, err := os.Create("/app/out/fuel_reversal_report.csv")
	if err != nil { return err }
	defer f.Close()
	w := csv.NewWriter(f)
	defer w.Flush()
	_ = w.Write([]string{"action_id","auth_id","fleet_id","batch_id","kind","amount","reason","status"})
	matchedCount, unmatchedCount, matchedAmount, unmatchedAmount := 0,0,0,0
	for _, act := range actions {
		best := -1
		for i, src := range sources {
			if strings.HasPrefix(src.authID, act.authID) || strings.HasPrefix(act.authID, src.authID) {
				if src.amount == act.amount && !src.used {
					best = i
					break
				}
			}
		}
		amt, _ := strconv.Atoi(strings.TrimSpace(act.amount))
		if best >= 0 {
			sources[best].used = true
			matchedCount++
			matchedAmount += amt
			_ = w.Write([]string{act.actionID, act.authID, act.fleetID, act.batchID, sources[best].kind, act.amount, act.reason, "MATCHED"})
		} else {
			unmatchedCount++
			unmatchedAmount += amt
			_ = w.Write([]string{act.actionID, act.authID, act.fleetID, act.batchID, "", act.amount, act.reason, "UNMATCHED"})
		}
	}
	body := fmt.Sprintf("matched_count=%d\nmatched_amount=%d\nunmatched_count=%d\nunmatched_amount=%d\n", matchedCount, matchedAmount, unmatchedCount, unmatchedAmount)
	return os.WriteFile(filepath.Clean("/app/out/fuel_reversal_summary.txt"), []byte(body), 0o644)
}
