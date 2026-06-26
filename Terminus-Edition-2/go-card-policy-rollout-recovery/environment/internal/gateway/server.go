package gateway

import (
	"cardrollout/internal/fsutil"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"os"
	"path/filepath"
	"time"
)

type ServerOptions struct {
	Region         string
	StatePath      string
	HoldGeneration int64
	StartedFile    string
	ReleaseFile    string
}

func NewStateFile(region, path string) (*StateFile, error) {
	s := &StateFile{path: path}
	if data, err := os.ReadFile(path); err == nil {
		if err := json.Unmarshal(data, &s.state); err != nil {
			return nil, err
		}
		if s.state.Region != region {
			return nil, fmt.Errorf("gateway state belongs to %s", s.state.Region)
		}
	} else if errors.Is(err, os.ErrNotExist) {
		s.state = PersistentState{
			Region:          region,
			Seen:            map[string]SeenCommand{},
			RequestAttempts: map[string]int64{},
			Audits:          []AuditEntry{},
		}
		if err := s.persistLocked(); err != nil {
			return nil, err
		}
	} else {
		return nil, err
	}
	if s.state.Seen == nil {
		s.state.Seen = map[string]SeenCommand{}
	}
	if s.state.RequestAttempts == nil {
		s.state.RequestAttempts = map[string]int64{}
	}
	return s, nil
}

func (s *StateFile) persistLocked() error {
	data, err := json.MarshalIndent(s.state, "", "  ")
	if err != nil {
		return err
	}
	return fsutil.AtomicWrite(s.path, append(data, '\n'), 0o600)
}

func (s *StateFile) Snapshot() PersistentState {
	s.mu.Lock()
	defer s.mu.Unlock()
	copyState := s.state
	copyState.Seen = make(map[string]SeenCommand, len(s.state.Seen))
	for k, v := range s.state.Seen {
		copyState.Seen[k] = v
	}
	copyState.RequestAttempts = make(map[string]int64, len(s.state.RequestAttempts))
	for k, v := range s.state.RequestAttempts {
		copyState.RequestAttempts[k] = v
	}
	copyState.Audits = append([]AuditEntry(nil), s.state.Audits...)
	return copyState
}

func Handler(state *StateFile, opts ServerOptions) http.Handler {
	mux := http.NewServeMux()
	mux.HandleFunc("/healthz", func(w http.ResponseWriter, _ *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_, _ = io.WriteString(w, `{"status":"ready"}`)
	})
	mux.HandleFunc("/debug/state", func(w http.ResponseWriter, _ *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(state.Snapshot())
	})
	mux.HandleFunc("/v1/policies/apply", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
			return
		}
		var req ApplyRequest
		dec := json.NewDecoder(io.LimitReader(r.Body, 2<<20))
		dec.DisallowUnknownFields()
		if err := dec.Decode(&req); err != nil {
			http.Error(w, "invalid request", http.StatusBadRequest)
			return
		}
		if req.CommandID == "" || req.RolloutID == "" || req.Generation <= 0 || req.PolicySHA256 == "" {
			http.Error(w, "missing fields", http.StatusBadRequest)
			return
		}
		if opts.HoldGeneration == req.Generation && opts.ReleaseFile != "" {
			if opts.StartedFile != "" {
				_ = os.MkdirAll(filepath.Dir(opts.StartedFile), 0o755)
				if marker, err := os.OpenFile(opts.StartedFile, os.O_CREATE|os.O_APPEND|os.O_WRONLY, 0o600); err == nil {
					_, _ = marker.WriteString("started\n")
					_ = marker.Close()
				}
			}
			for {
				if _, err := os.Stat(opts.ReleaseFile); err == nil {
					break
				}
				select {
				case <-r.Context().Done():
					return
				case <-time.After(10 * time.Millisecond):
				}
			}
		}
		resp, code, err := state.Apply(req)
		if err != nil {
			http.Error(w, err.Error(), http.StatusInternalServerError)
			return
		}
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(code)
		_ = json.NewEncoder(w).Encode(resp)
	})
	return mux
}

func (s *StateFile) Apply(req ApplyRequest) (ApplyResponse, int, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.state.RequestAttempts[req.CommandID]++
	if seen, ok := s.state.Seen[req.CommandID]; ok {
		if err := s.persistLocked(); err != nil {
			return ApplyResponse{}, 0, err
		}
		code := http.StatusOK
		if seen.Status == "stale" || seen.Status == "conflict" {
			code = http.StatusConflict
		}
		return ApplyResponse{
			Status:           seen.Status,
			Region:           s.state.Region,
			CommandID:        req.CommandID,
			ActiveGeneration: seen.ActiveGeneration,
			Sequence:         seen.Sequence,
			PolicySHA256:     seen.PolicySHA256,
		}, code, nil
	}

	status := "applied"
	code := http.StatusOK
	if req.Generation < s.state.ActiveGeneration {
		status = "stale"
		code = http.StatusConflict
	} else if req.Generation == s.state.ActiveGeneration && s.state.ActiveGeneration != 0 {
		if req.PolicySHA256 == s.state.PolicySHA256 {
			status = "already-active"
		} else {
			status = "conflict"
			code = http.StatusConflict
		}
	} else {
		s.state.ActiveGeneration = req.Generation
		s.state.PolicySHA256 = req.PolicySHA256
		s.state.Sequence++
		s.state.Audits = append(s.state.Audits, AuditEntry{
			CommandID:    req.CommandID,
			RolloutID:    req.RolloutID,
			Generation:   req.Generation,
			PolicySHA256: req.PolicySHA256,
			Sequence:     s.state.Sequence,
		})
	}
	seen := SeenCommand{
		Status:           status,
		ActiveGeneration: s.state.ActiveGeneration,
		Sequence:         s.state.Sequence,
		PolicySHA256:     s.state.PolicySHA256,
	}
	s.state.Seen[req.CommandID] = seen
	if err := s.persistLocked(); err != nil {
		return ApplyResponse{}, 0, err
	}
	return ApplyResponse{
		Status:           status,
		Region:           s.state.Region,
		CommandID:        req.CommandID,
		ActiveGeneration: s.state.ActiveGeneration,
		Sequence:         s.state.Sequence,
		PolicySHA256:     s.state.PolicySHA256,
	}, code, nil
}
