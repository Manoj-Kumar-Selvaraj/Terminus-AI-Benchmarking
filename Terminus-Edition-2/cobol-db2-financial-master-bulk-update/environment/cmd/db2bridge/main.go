package main

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strconv"
	"strings"

	"finbulk/internal/db2sim"
	"finbulk/internal/finbulk"
)

func env(name string, fallback ...string) string {
	if v := os.Getenv(name); v != "" {
		return v
	}
	for _, k := range fallback {
		if v := os.Getenv(k); v != "" {
			return v
		}
	}
	return ""
}

func writeResult(value string) {
	if path := env("BRIDGE_RESULT"); path != "" {
		_ = os.WriteFile(path, []byte(value+"\n"), 0o644)
		return
	}
	fmt.Println(value)
}

func atoi(s string) int {
	v, _ := strconv.Atoi(strings.TrimSpace(s))
	return v
}

func num(v any) int {
	switch t := v.(type) {
	case float64:
		return int(t)
	case int:
		return t
	case json.Number:
		i, _ := t.Int64()
		return int(i)
	default:
		return 0
	}
}

func loadDB() (db2sim.DB, error) {
	p := env("BRIDGE_DB", "FINBULK_DB")
	if p == "" {
		return nil, fmt.Errorf("BRIDGE_DB is required")
	}
	return db2sim.Load(p)
}

func saveDB(db db2sim.DB) error {
	p := env("BRIDGE_DB", "FINBULK_DB")
	if p == "" {
		return fmt.Errorf("BRIDGE_DB is required")
	}
	return db2sim.Save(p, db)
}

func applyDetail(db db2sim.DB, batchID string, seq int, account, op string, amount int, eventID string, checkDuplicate, atomicLimit bool) int {
	if checkDuplicate {
		if dup := db2sim.EnsureNotDuplicate(db, batchID, seq); dup != db2sim.OK {
			return dup
		}
	}
	var code int
	switch op {
	case "BAL":
		code = db2sim.UpdateBalance(db, account, amount)
		if code == db2sim.OK {
			db2sim.AppendLedger(db, batchID, seq, account, amount, eventID)
		}
	case "RAT":
		code = db2sim.UpdateRate(db, account, amount)
	case "HLD":
		code = db2sim.UpdateHold(db, account, amount)
	case "LIM":
		if atomicLimit {
			staged := db2sim.Clone(db)
			code = db2sim.UpdateMasterLimit(staged, account, amount)
			if code == db2sim.OK {
				code = db2sim.UpdateRiskLimit(staged, account, amount)
			}
			if code == db2sim.OK {
				db2sim.CommitSnapshot(db, staged)
			}
		} else {
			code = db2sim.UpdateMasterLimit(db, account, amount)
			if code == db2sim.OK {
				code = db2sim.UpdateRiskLimit(db, account, amount)
			}
		}
	default:
		code = db2sim.Constraint
	}
	if code == db2sim.OK {
		db2sim.AppendAudit(db, batchID, seq, account, op, code, eventID)
		db2sim.MarkApplied(db, batchID, seq, eventID, account, op)
	}
	return code
}

func inputHash(path string) (string, error) {
	b, err := os.ReadFile(path)
	if err != nil {
		return "", err
	}
	s := sha256.Sum256(b)
	return hex.EncodeToString(s[:]), nil
}

func loadControl(controlPath string, h finbulk.Header, details []finbulk.Detail, tr finbulk.Trailer, inputPath string) (map[string]any, string, error) {
	hsh, err := inputHash(inputPath)
	if err != nil {
		return nil, "", err
	}
	if controlPath == "" {
		return nil, hsh, nil
	}
	raw, err := os.ReadFile(controlPath)
	if err != nil {
		return nil, hsh, fmt.Errorf("malformed control manifest: %w", err)
	}
	var control map[string]any
	if err := json.Unmarshal(raw, &control); err != nil {
		return nil, hsh, fmt.Errorf("malformed control manifest: %w", err)
	}
	if control["batch_id"] != h.BatchID {
		return nil, hsh, fmt.Errorf("control batch id mismatch")
	}
	if control["business_date"] != h.BusinessDate {
		return nil, hsh, fmt.Errorf("control business date mismatch")
	}
	if control["source"] != h.Source {
		return nil, hsh, fmt.Errorf("control source mismatch")
	}
	if num(control["expected_detail_count"]) != len(details) {
		return nil, hsh, fmt.Errorf("control detail count mismatch")
	}
	if num(control["expected_financial_total"]) != tr.Total {
		return nil, hsh, fmt.Errorf("control financial total mismatch")
	}
	return control, hsh, nil
}

func enforceControlReplay(db db2sim.DB, batchID, inputHash string) error {
	totals, _ := db["control_totals"].(map[string]any)
	if totals == nil {
		return nil
	}
	entry, _ := totals[batchID].(map[string]any)
	if entry != nil && entry["input_sha256"] != inputHash {
		return fmt.Errorf("duplicate batch id with different input hash")
	}
	return nil
}

func recordControlTotal(db db2sim.DB, batchID string, control map[string]any, inputHash string, status string, pendingLocks int) {
	if control == nil {
		return
	}
	final := status
	if status == "OK" && pendingLocks == 0 {
		final = "SETTLED"
	}
	totals, _ := db["control_totals"].(map[string]any)
	if totals == nil {
		totals = map[string]any{}
		db["control_totals"] = totals
	}
	totals[batchID] = map[string]any{
		"batch_id":        batchID,
		"business_date":   control["business_date"],
		"source":          control["source"],
		"detail_count":    num(control["expected_detail_count"]),
		"financial_total": num(control["expected_financial_total"]),
		"input_sha256":    inputHash,
		"status":          final,
	}
}

func main() {
	if len(os.Args) < 2 {
		writeResult("operation required")
		os.Exit(1)
	}
	if err := run(os.Args[1]); err != nil {
		writeResult(err.Error())
		os.Exit(1)
	}
}

func run(cmd string) error {
	switch cmd {
	case "load":
		_, err := loadDB()
		if err != nil {
			return err
		}
		writeResult("0")
		return nil
	case "save":
		db, err := loadDB()
		if err != nil {
			return err
		}
		if err := saveDB(db); err != nil {
			return err
		}
		writeResult("0")
		return nil
	case "is-applied":
		db, err := loadDB()
		if err != nil {
			return err
		}
		if db2sim.IsApplied(db, env("BRIDGE_BATCH", "FINBULK_BATCH"), atoi(env("BRIDGE_SEQ"))) {
			writeResult("1")
		} else {
			writeResult("0")
		}
		return nil
	case "apply-detail":
		db, err := loadDB()
		if err != nil {
			return err
		}
		flags := map[string]bool{}
		for _, part := range strings.Split(env("BRIDGE_FLAGS"), ",") {
			if s := strings.TrimSpace(part); s != "" {
				flags[s] = true
			}
		}
		code := applyDetail(db, env("BRIDGE_BATCH", "FINBULK_BATCH"), atoi(env("BRIDGE_SEQ")), env("BRIDGE_ACCOUNT"), env("BRIDGE_OP"), atoi(env("BRIDGE_AMOUNT")), env("BRIDGE_EVENT_ID"), flags["check-duplicate"], flags["atomic-lim"])
		if err := saveDB(db); err != nil {
			return err
		}
		writeResult(strconv.Itoa(code))
		return nil
	case "append-reject":
		db, err := loadDB()
		if err != nil {
			return err
		}
		db2sim.AppendReject(db, env("BRIDGE_BATCH", "FINBULK_BATCH"), atoi(env("BRIDGE_SEQ")), env("BRIDGE_ACCOUNT"), atoi(env("BRIDGE_SQLCODE")), env("BRIDGE_REASON", "BUSINESS_REJECT"), env("BRIDGE_EVENT_ID"))
		if err := saveDB(db); err != nil {
			return err
		}
		writeResult("0")
		return nil
	case "append-pending-lock":
		db, err := loadDB()
		if err != nil {
			return err
		}
		holder := "UNKNOWN"
		if locks, _ := db["locks"].(map[string]any); locks != nil {
			if h, ok := locks[env("BRIDGE_ACCOUNT")].(string); ok {
				holder = h
			}
		}
		db2sim.AppendPendingLock(db, env("BRIDGE_BATCH", "FINBULK_BATCH"), atoi(env("BRIDGE_SEQ")), env("BRIDGE_ACCOUNT"), holder, env("BRIDGE_EVENT_ID"))
		if err := saveDB(db); err != nil {
			return err
		}
		writeResult("0")
		return nil
	case "write-outputs":
		db, err := loadDB()
		if err != nil {
			return err
		}
		summary := finbulk.Summary{"batch_id": env("BRIDGE_BATCH", "FINBULK_BATCH"), "applied": atoi(env("BRIDGE_APPLIED")), "rejected": atoi(env("BRIDGE_REJECTED")), "skipped": atoi(env("BRIDGE_SKIPPED")), "status": env("BRIDGE_STATUS")}
		if summary["status"] == "" {
			summary["status"] = "OK"
		}
		if v := env("BRIDGE_PENDING_LOCKS"); v != "" {
			summary["pending_locks"] = atoi(v)
		}
		if v := env("BRIDGE_LAST_SQLCODE"); v != "" {
			summary["last_sqlcode"] = atoi(v)
		}
		if v := env("BRIDGE_ERROR"); v != "" {
			summary["error"] = v
		}
		if err := finbulk.WriteOutputs(env("BRIDGE_OUT", "FINBULK_OUT"), env("BRIDGE_BATCH", "FINBULK_BATCH"), summary, db); err != nil {
			return err
		}
		writeResult("0")
		return nil
	case "failed-closed":
		db, err := loadDB()
		if err != nil {
			return err
		}
		summary := finbulk.Summary{"batch_id": env("BRIDGE_BATCH", "FINBULK_BATCH"), "status": "FAILED_CLOSED", "error": env("BRIDGE_ERROR"), "applied": 0, "rejected": 0, "skipped": 0}
		if summary["error"] == "" {
			summary["error"] = "validation failure"
		}
		if err := finbulk.WriteOutputs(env("BRIDGE_OUT", "FINBULK_OUT"), env("BRIDGE_BATCH", "FINBULK_BATCH"), summary, db); err != nil {
			return err
		}
		writeResult("0")
		return nil
	case "input-hash":
		h, err := inputHash(env("BRIDGE_INPUT"))
		if err != nil {
			return err
		}
		writeResult(h)
		return nil
	case "validate-control":
		input := env("BRIDGE_INPUT")
		h, details, tr, err := finbulk.ParseFile(input)
		if err != nil {
			return err
		}
		_, digest, err := loadControl(env("BRIDGE_CONTROL"), h, details, tr, input)
		if err != nil {
			return err
		}
		writeResult(digest)
		return nil
	case "enforce-control-replay":
		db, err := loadDB()
		if err != nil {
			return err
		}
		if err := enforceControlReplay(db, env("BRIDGE_BATCH", "FINBULK_BATCH"), env("BRIDGE_INPUT_HASH")); err != nil {
			return err
		}
		if err := saveDB(db); err != nil {
			return err
		}
		writeResult("0")
		return nil
	case "record-control-total":
		db, err := loadDB()
		if err != nil {
			return err
		}
		var control map[string]any
		if p := env("BRIDGE_CONTROL"); p != "" {
			raw, err := os.ReadFile(p)
			if err != nil {
				return err
			}
			if err := json.Unmarshal(raw, &control); err != nil {
				return err
			}
		}
		recordControlTotal(db, env("BRIDGE_BATCH", "FINBULK_BATCH"), control, env("BRIDGE_INPUT_HASH"), env("BRIDGE_STATUS"), atoi(env("BRIDGE_PENDING_LOCKS")))
		if err := saveDB(db); err != nil {
			return err
		}
		writeResult("0")
		return nil
	default:
		return fmt.Errorf("unknown operation: %s", cmd)
	}
}

func init() {
	_ = filepath.Separator
}
