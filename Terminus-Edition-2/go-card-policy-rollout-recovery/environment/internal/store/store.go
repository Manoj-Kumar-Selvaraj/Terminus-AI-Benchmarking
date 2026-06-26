package store

import (
	"bytes"
	"cardrollout/internal/fsutil"
	"cardrollout/internal/model"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"os"
	"path/filepath"
)

type Store struct {
	Dir string
}

func New(dir string) *Store {
	return &Store{Dir: dir}
}

func (s *Store) lockPath() string     { return filepath.Join(s.Dir, "controller.lock") }
func (s *Store) journalPath() string  { return filepath.Join(s.Dir, "journal.jsonl") }
func (s *Store) snapshotPath() string { return filepath.Join(s.Dir, "snapshot.json") }

func (s *Store) WithLock(fn func(*model.State) error) error {
	lock, err := fsutil.Acquire(s.lockPath())
	if err != nil {
		return err
	}
	defer lock.Close()
	state, err := s.loadUnlocked()
	if err != nil {
		return err
	}
	return fn(state)
}

func (s *Store) Read() (*model.State, error) {
	lock, err := fsutil.Acquire(s.lockPath())
	if err != nil {
		return nil, err
	}
	defer lock.Close()
	return s.loadUnlocked()
}

func (s *Store) loadUnlocked() (*model.State, error) {
	if err := os.MkdirAll(s.Dir, 0o755); err != nil {
		return nil, err
	}
	state := model.NewState()
	var offset int64
	if data, err := os.ReadFile(s.snapshotPath()); err == nil {
		var snap snapshotFile
		if err := json.Unmarshal(data, &snap); err != nil {
			return nil, fmt.Errorf("decode snapshot: %w", err)
		}
		if snap.SchemaVersion != 2 || snap.State == nil {
			return nil, errors.New("unsupported snapshot")
		}
		state = snap.State
		if state.Rollouts == nil {
			state.Rollouts = map[string]*model.Rollout{}
		}
		if state.ActiveGeneration == nil {
			state.ActiveGeneration = map[string]int64{}
		}
		offset = snap.JournalOffset
	} else if !errors.Is(err, os.ErrNotExist) {
		return nil, err
	}

	data, err := os.ReadFile(s.journalPath())
	if errors.Is(err, os.ErrNotExist) {
		return state, nil
	}
	if err != nil {
		return nil, err
	}
	if offset > int64(len(data)) {
		offset = 0
	}
	body := data[offset:]
	parts := bytes.Split(body, []byte("\n"))
	for i, part := range parts {
		if len(part) == 0 {
			continue
		}
		event, decodeErr := model.DecodeEvent(part, false)
		if decodeErr != nil {
			return nil, fmt.Errorf("journal line %d: %w", i+1, decodeErr)
		}
		if err := model.ApplyEvent(state, event); err != nil {
			return nil, fmt.Errorf("apply journal line %d: %w", i+1, err)
		}
	}
	return state, nil
}

func (s *Store) recoverTailUnlocked(full []byte, start int, tail []byte) error {
	recovery := filepath.Join(s.Dir, "recovery", "torn-tail.bin")
	if current, err := os.ReadFile(recovery); err == nil {
		if !bytes.Equal(current, tail) {
			return errors.New("existing torn-tail recovery artifact differs")
		}
	} else if errors.Is(err, os.ErrNotExist) {
		if err := fsutil.AtomicWrite(recovery, tail, 0o600); err != nil {
			return err
		}
	} else {
		return err
	}
	f, err := os.OpenFile(s.journalPath(), os.O_WRONLY, 0o600)
	if err != nil {
		return err
	}
	if err := f.Truncate(int64(start)); err != nil {
		f.Close()
		return err
	}
	if err := f.Sync(); err != nil {
		f.Close()
		return err
	}
	return f.Close()
}

func (s *Store) Append(event model.Event) error {
	if event.Version == 0 {
		event.Version = 2
	}
	payload, err := json.Marshal(event)
	if err != nil {
		return err
	}
	if err := os.MkdirAll(s.Dir, 0o755); err != nil {
		return err
	}
	path := s.journalPath()
	f, err := os.OpenFile(path, os.O_CREATE|os.O_RDWR, 0o600)
	if err != nil {
		return err
	}
	defer f.Close()
	info, err := f.Stat()
	if err != nil {
		return err
	}
	if info.Size() > 0 {
		last := []byte{0}
		if _, err := f.ReadAt(last, info.Size()-1); err != nil && !errors.Is(err, io.EOF) {
			return err
		}
		if last[0] != '\n' {
			if _, err := f.WriteAt([]byte("\n"), info.Size()); err != nil {
				return err
			}
		}
	}
	if _, err := f.Seek(0, io.SeekEnd); err != nil {
		return err
	}
	if _, err := f.Write(append(payload, '\n')); err != nil {
		return err
	}
	return f.Sync()
}

func (s *Store) Compact(failpoint string) error {
	lock, err := fsutil.Acquire(s.lockPath())
	if err != nil {
		return err
	}
	defer lock.Close()
	state, err := s.loadUnlocked()
	if err != nil {
		return err
	}
	var journalSize int64
	if info, err := os.Stat(s.journalPath()); err == nil {
		journalSize = info.Size()
	} else if !errors.Is(err, os.ErrNotExist) {
		return err
	}
	if err := s.writeSnapshotUnlocked(state, journalSize); err != nil {
		return err
	}
	if failpoint == "after-snapshot-rename" {
		return ErrInjectedCompactionStop
	}
	f, err := os.OpenFile(s.journalPath(), os.O_CREATE|os.O_TRUNC|os.O_WRONLY, 0o600)
	if err != nil {
		return err
	}
	if err := f.Sync(); err != nil {
		f.Close()
		return err
	}
	if err := f.Close(); err != nil {
		return err
	}
	return s.writeSnapshotUnlocked(state, 0)
}

func (s *Store) writeSnapshotUnlocked(state *model.State, offset int64) error {
	snap := snapshotFile{SchemaVersion: 2, JournalOffset: offset, State: state}
	data, err := json.MarshalIndent(snap, "", "  ")
	if err != nil {
		return err
	}
	data = append(data, '\n')
	return fsutil.AtomicWrite(s.snapshotPath(), data, 0o600)
}

var ErrInjectedCompactionStop = errors.New("injected stop after snapshot rename")
