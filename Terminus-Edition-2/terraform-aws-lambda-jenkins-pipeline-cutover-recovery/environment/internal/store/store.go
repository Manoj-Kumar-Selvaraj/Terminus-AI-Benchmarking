package store

import (
	"bufio"
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"strings"

	"jenkins-lambda-cutover/internal/model"
)

const StateRoot = "/app/state"

func ensure() error { return os.MkdirAll(StateRoot, 0o755) }

func AtomicWriteJSON(path string, value any) error {
	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
		return err
	}
	data, err := json.MarshalIndent(value, "", "  ")
	if err != nil {
		return err
	}
	tmp, err := os.CreateTemp(filepath.Dir(path), ".tmp-*")
	if err != nil {
		return err
	}
	name := tmp.Name()
	defer os.Remove(name)
	if err := tmp.Chmod(0o600); err != nil {
		tmp.Close()
		return err
	}
	if _, err := tmp.Write(append(data, '\n')); err != nil {
		tmp.Close()
		return err
	}
	if err := tmp.Sync(); err != nil {
		tmp.Close()
		return err
	}
	if err := tmp.Close(); err != nil {
		return err
	}
	return os.Rename(name, path)
}

func ReadJSON(path string, out any) error {
	data, err := os.ReadFile(path)
	if err != nil {
		return err
	}
	return json.Unmarshal(data, out)
}

func SaveCheckpoint(cp model.Checkpoint) error {
	if err := ensure(); err != nil {
		return err
	}
	return AtomicWriteJSON(filepath.Join(StateRoot, "executions", cp.ExecutionID+".json"), cp)
}

func LoadCheckpoint(id string) (model.Checkpoint, error) {
	var cp model.Checkpoint
	err := ReadJSON(filepath.Join(StateRoot, "executions", id+".json"), &cp)
	return cp, err
}

func ListCheckpoints() ([]model.Checkpoint, error) {
	dir := filepath.Join(StateRoot, "executions")
	entries, err := os.ReadDir(dir)
	if errors.Is(err, os.ErrNotExist) {
		return nil, nil
	}
	if err != nil {
		return nil, err
	}
	var out []model.Checkpoint
	for _, entry := range entries {
		if entry.IsDir() || !strings.HasSuffix(entry.Name(), ".json") {
			continue
		}
		var cp model.Checkpoint
		if err := ReadJSON(filepath.Join(dir, entry.Name()), &cp); err != nil {
			return nil, err
		}
		out = append(out, cp)
	}
	return out, nil
}

func SaveDeployment(d model.Deployment) error {
	if err := ensure(); err != nil {
		return err
	}
	return AtomicWriteJSON(filepath.Join(StateRoot, fmt.Sprintf("deployment-%d.json", d.Generation)), d)
}

func LoadDeployment(generation int) (model.Deployment, error) {
	var d model.Deployment
	err := ReadJSON(filepath.Join(StateRoot, fmt.Sprintf("deployment-%d.json", generation)), &d)
	return d, err
}

func SaveCutover(c model.CutoverState) error {
	return AtomicWriteJSON(filepath.Join(StateRoot, "cutover.json"), c)
}
func LoadCutover() (model.CutoverState, error) {
	var c model.CutoverState
	err := ReadJSON(filepath.Join(StateRoot, "cutover.json"), &c)
	return c, err
}

func AppendJournal(r model.JournalRecord) error {
	if err := ensure(); err != nil {
		return err
	}
	path := filepath.Join(StateRoot, "operations.journal.jsonl")
	f, err := os.OpenFile(path, os.O_CREATE|os.O_APPEND|os.O_WRONLY, 0o600)
	if err != nil {
		return err
	}
	defer f.Close()
	data, err := json.Marshal(r)
	if err != nil {
		return err
	}
	if _, err := f.Write(append(data, '\n')); err != nil {
		return err
	}
	return f.Sync()
}

func ReadJournalTolerant() ([]model.JournalRecord, bool, error) {
	path := filepath.Join(StateRoot, "operations.journal.jsonl")
	f, err := os.Open(path)
	if errors.Is(err, os.ErrNotExist) {
		return nil, false, nil
	}
	if err != nil {
		return nil, false, err
	}
	defer f.Close()
	var records []model.JournalRecord
	corruptTail := false
	s := bufio.NewScanner(f)
	for s.Scan() {
		line := strings.TrimSpace(s.Text())
		if line == "" {
			continue
		}
		var r model.JournalRecord
		if err := json.Unmarshal([]byte(line), &r); err != nil {
			corruptTail = true
			break
		}
		records = append(records, r)
	}
	return records, corruptTail, s.Err()
}

func RewriteJournal(records []model.JournalRecord) error {
	if err := ensure(); err != nil {
		return err
	}
	path := filepath.Join(StateRoot, "operations.journal.jsonl")
	tmp, err := os.CreateTemp(StateRoot, ".journal-*")
	if err != nil {
		return err
	}
	name := tmp.Name()
	defer os.Remove(name)
	for _, r := range records {
		data, err := json.Marshal(r)
		if err != nil {
			tmp.Close()
			return err
		}
		if _, err := tmp.Write(append(data, '\n')); err != nil {
			tmp.Close()
			return err
		}
	}
	if err := tmp.Sync(); err != nil {
		tmp.Close()
		return err
	}
	if err := tmp.Close(); err != nil {
		return err
	}
	return os.Rename(name, path)
}
