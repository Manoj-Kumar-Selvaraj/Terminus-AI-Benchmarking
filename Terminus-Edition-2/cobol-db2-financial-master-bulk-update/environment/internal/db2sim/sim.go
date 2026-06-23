package db2sim

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strings"
)

const (
	OK           = 0
	NotFound     = 100
	LockTimeout  = -911
	Duplicate    = -803
	Constraint   = -530
)

type DB map[string]any

func Load(path string) (DB, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	var db DB
	if err := json.Unmarshal(data, &db); err != nil {
		return nil, err
	}
	defaults := map[string]any{
		"master": map[string]any{}, "risk": map[string]any{}, "locks": map[string]any{},
		"ledger": []any{}, "audit": []any{}, "rejects": []any{}, "pending_locks": []any{},
		"checkpoint": map[string]any{}, "applied_events": map[string]any{},
	}
	for k, v := range defaults {
		if _, ok := db[k]; !ok {
			db[k] = v
		}
	}
	return db, nil
}

func Save(path string, db DB) error {
	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
		return err
	}
	tmp := path + ".tmp"
	f, err := os.Create(tmp)
	if err != nil {
		return err
	}
	enc := json.NewEncoder(f)
	enc.SetIndent("", "  ")
	enc.SetEscapeHTML(false)
	if err := enc.Encode(db); err != nil {
		f.Close()
		return err
	}
	if err := f.Close(); err != nil {
		return err
	}
	return os.Rename(tmp, path)
}

func Clone(db DB) DB {
	b, _ := json.Marshal(db)
	var out DB
	_ = json.Unmarshal(b, &out)
	return out
}

func eventKey(batchID string, seq int) string {
	return fmt.Sprintf("%s|%06d", batchID, seq)
}

func IsApplied(db DB, batchID string, seq int) bool {
	events, _ := db["applied_events"].(map[string]any)
	if events == nil {
		return false
	}
	_, ok := events[eventKey(batchID, seq)]
	return ok
}

func masterRow(db DB, account string) (int, map[string]any) {
	account = strings.TrimSpace(account)
	if locks, _ := db["locks"].(map[string]any); locks != nil {
		if _, locked := locks[account]; locked {
			return LockTimeout, nil
		}
	}
	master, _ := db["master"].(map[string]any)
	if master == nil {
		return NotFound, nil
	}
	row, ok := master[account].(map[string]any)
	if !ok || row == nil {
		return NotFound, nil
	}
	return OK, row
}

func EnsureNotDuplicate(db DB, batchID string, seq int) int {
	if IsApplied(db, batchID, seq) {
		return Duplicate
	}
	return OK
}

func UpdateBalance(db DB, account string, delta int) int {
	code, row := masterRow(db, account)
	if code != OK {
		return code
	}
	bal, _ := row["balance_cents"].(float64)
	row["balance_cents"] = int(bal) + delta
	return OK
}

func UpdateRate(db DB, account string, rateBP int) int {
	code, row := masterRow(db, account)
	if code != OK {
		return code
	}
	if rateBP < 0 || rateBP > 3000 {
		return Constraint
	}
	row["rate_bp"] = rateBP
	return OK
}

func UpdateHold(db DB, account string, flagValue int) int {
	code, row := masterRow(db, account)
	if code != OK {
		return code
	}
	flag := "N"
	if flagValue != 0 {
		flag = "Y"
	}
	row["hold_flag"] = flag
	if risk, _ := db["risk"].(map[string]any); risk != nil {
		if rr, ok := risk[account].(map[string]any); ok {
			rr["hold_flag"] = flag
		}
	}
	return OK
}

func UpdateMasterLimit(db DB, account string, newLimit int) int {
	code, row := masterRow(db, account)
	if code != OK {
		return code
	}
	if newLimit < 0 {
		return Constraint
	}
	row["credit_limit_cents"] = newLimit
	return OK
}

func UpdateRiskLimit(db DB, account string, newLimit int) int {
	if locks, _ := db["locks"].(map[string]any); locks != nil {
		if _, locked := locks[account]; locked {
			return LockTimeout
		}
	}
	risk, _ := db["risk"].(map[string]any)
	master, _ := db["master"].(map[string]any)
	riskRow, okR := risk[account].(map[string]any)
	masterRow, okM := master[account].(map[string]any)
	if !okR || !okM {
		return Constraint
	}
	bal, _ := masterRow["balance_cents"].(float64)
	if newLimit < int(bal) {
		return Constraint
	}
	riskRow["exposure_limit_cents"] = newLimit
	return OK
}

func AppendLedger(db DB, batchID string, seq int, account string, delta int, eventID string) {
	ledger, _ := db["ledger"].([]any)
	db["ledger"] = append(ledger, map[string]any{
		"batch_id": batchID, "seq": seq, "account": account,
		"delta_cents": delta, "event_id": eventID,
	})
}

func AppendAudit(db DB, batchID string, seq int, account, op string, sqlcode int, eventID string) {
	audit, _ := db["audit"].([]any)
	db["audit"] = append(audit, map[string]any{
		"batch_id": batchID, "seq": seq, "account": account,
		"op": op, "sqlcode": sqlcode, "event_id": eventID,
	})
}

func MarkApplied(db DB, batchID string, seq int, eventID, account, op string) {
	events, _ := db["applied_events"].(map[string]any)
	if events == nil {
		events = map[string]any{}
		db["applied_events"] = events
	}
	events[eventKey(batchID, seq)] = map[string]any{
		"event_id": eventID, "account": account, "op": op,
	}
	checkpoint, _ := db["checkpoint"].(map[string]any)
	if checkpoint == nil {
		checkpoint = map[string]any{}
		db["checkpoint"] = checkpoint
	}
	prev, _ := checkpoint[batchID].(float64)
	if seq > int(prev) {
		checkpoint[batchID] = seq
	}
}

func AppendReject(db DB, batchID string, seq int, account string, sqlcode int, reason, eventID string) {
	rejects, _ := db["rejects"].([]any)
	db["rejects"] = append(rejects, map[string]any{
		"batch_id": batchID, "seq": seq, "account": account,
		"sqlcode": sqlcode, "reason": reason, "event_id": eventID,
	})
}

func AppendPendingLock(db DB, batchID string, seq int, account, holder, eventID string) {
	locks, _ := db["pending_locks"].([]any)
	db["pending_locks"] = append(locks, map[string]any{
		"batch_id": batchID, "seq": seq, "account": account,
		"sqlcode": LockTimeout, "lock_holder": holder, "event_id": eventID,
	})
}

func CommitSnapshot(dst, staged DB) {
	for k := range dst {
		delete(dst, k)
	}
	for k, v := range staged {
		dst[k] = v
	}
}
