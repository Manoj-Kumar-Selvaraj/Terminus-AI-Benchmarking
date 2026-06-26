package main

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"sort"
	"strconv"
	"strings"
	"sync"
	"syscall"
	"time"
)

const root = "/var/lib/lambda-pipeline-runtime"
const statePath = root + "/state.json"

var mu sync.Mutex

type StageConfig struct {
	Name                string   `json:"name"`
	FunctionName        string   `json:"function_name"`
	TimeoutSeconds      int      `json:"timeout_seconds"`
	ReservedConcurrency int      `json:"reserved_concurrency"`
	MemoryMB            int      `json:"memory_mb"`
	Permissions         []string `json:"permissions"`
	Alias               string   `json:"alias"`
	PackageHash         string   `json:"package_hash"`
}
type Deployment struct {
	Generation int           `json:"generation"`
	Alias      string        `json:"alias"`
	Module     string        `json:"module"`
	Version    string        `json:"version"`
	Digest     string        `json:"digest"`
	Stages     []StageConfig `json:"stages"`
}
type Invocation struct {
	Stage          string            `json:"stage"`
	ExecutionID    string            `json:"execution_id"`
	BatchID        string            `json:"batch_id"`
	ItemID         string            `json:"item_id,omitempty"`
	Attempt        int               `json:"attempt"`
	Generation     int               `json:"generation"`
	Epoch          int64             `json:"epoch"`
	Owner          string            `json:"owner"`
	IdempotencyKey string            `json:"idempotency_key,omitempty"`
	Metadata       map[string]string `json:"metadata,omitempty"`
}
type InvocationResult struct {
	OK           bool              `json:"ok"`
	Class        string            `json:"class,omitempty"`
	Message      string            `json:"message,omitempty"`
	LostResponse bool              `json:"lost_response,omitempty"`
	Duplicate    bool              `json:"duplicate,omitempty"`
	Output       map[string]string `json:"output,omitempty"`
}
type Effect struct {
	LogicalKey     string `json:"logical_key"`
	IdempotencyKey string `json:"idempotency_key"`
	Stage          string `json:"stage"`
	ExecutionID    string `json:"execution_id"`
	BatchID        string `json:"batch_id"`
	ItemID         string `json:"item_id,omitempty"`
	Generation     int    `json:"generation"`
	Count          int    `json:"count"`
}
type RuntimeState struct {
	Now                  string                `json:"now"`
	Failures             map[string]int        `json:"failures"`
	Deployments          map[string]Deployment `json:"deployments"`
	ActiveGeneration     int                   `json:"active_generation"`
	Writer               string                `json:"writer"`
	Epoch                int64                 `json:"epoch"`
	Effects              []Effect              `json:"effects"`
	Locks                map[string]string     `json:"locks"`
	Invocations          []Invocation          `json:"invocations"`
	DLQ                  map[string][]string   `json:"dlq"`
	Drift                map[string]bool       `json:"drift"`
	JenkinsWrites        int                   `json:"jenkins_writes"`
	ExecutionEpochs      map[string]int64      `json:"execution_epochs"`
	ExecutionGenerations map[string]int        `json:"execution_generations"`
	BatchExecutions      map[string]string     `json:"batch_executions"`
}

func initial() RuntimeState {
	return RuntimeState{Now: "2026-06-23T10:00:00Z", Failures: map[string]int{}, Deployments: map[string]Deployment{}, Writer: "jenkins", Epoch: 1, Locks: map[string]string{}, DLQ: map[string][]string{}, Drift: map[string]bool{}}
}
func load() (RuntimeState, error) {
	b, err := os.ReadFile(statePath)
	if errors.Is(err, os.ErrNotExist) {
		s := initial()
		return s, nil
	}
	if err != nil {
		return RuntimeState{}, err
	}
	var s RuntimeState
	if err := json.Unmarshal(b, &s); err != nil {
		return RuntimeState{}, err
	}
	if s.Failures == nil {
		s.Failures = map[string]int{}
	}
	if s.Deployments == nil {
		s.Deployments = map[string]Deployment{}
	}
	if s.Locks == nil {
		s.Locks = map[string]string{}
	}
	if s.DLQ == nil {
		s.DLQ = map[string][]string{}
	}
	if s.Drift == nil {
		s.Drift = map[string]bool{}
	}
	if s.Effects == nil {
		s.Effects = []Effect{}
	}
	if s.Invocations == nil {
		s.Invocations = []Invocation{}
	}
	if s.ExecutionEpochs == nil {
		s.ExecutionEpochs = map[string]int64{}
	}
	if s.ExecutionGenerations == nil {
		s.ExecutionGenerations = map[string]int{}
	}
	if s.BatchExecutions == nil {
		s.BatchExecutions = map[string]string{}
	}
	return s, nil
}
func save(s RuntimeState) error {
	if err := os.MkdirAll(root, 0o755); err != nil {
		return err
	}
	b, err := json.MarshalIndent(s, "", "  ")
	if err != nil {
		return err
	}
	tmp := statePath + ".tmp"
	if err := os.WriteFile(tmp, append(b, '\n'), 0o600); err != nil {
		return err
	}
	return os.Rename(tmp, statePath)
}
func decode(out any) error { return json.NewDecoder(os.Stdin).Decode(out) }
func encode(v any)         { _ = json.NewEncoder(os.Stdout).Encode(v) }
func consume(s *RuntimeState, key string) bool {
	if s.Failures[key] > 0 {
		s.Failures[key]--
		return true
	}
	return false
}
func stageMap(d Deployment) map[string]StageConfig {
	m := map[string]StageConfig{}
	for _, st := range d.Stages {
		m[st.Name] = st
	}
	return m
}
func logicalKey(i Invocation) string {
	switch i.Stage {
	case "write_ledger":
		return i.BatchID + "/ledger/" + i.ItemID
	case "build_report":
		return i.BatchID + "/report"
	case "notify_partner":
		return i.BatchID + "/notify"
	case "archive_batch":
		return i.BatchID + "/archive"
	}
	return ""
}
func applyEffect(s *RuntimeState, i Invocation) (bool, error) {
	key := logicalKey(i)
	if key == "" {
		return false, nil
	}
	if i.IdempotencyKey == "" {
		return false, fmt.Errorf("missing idempotency key")
	}
	for x := range s.Effects {
		if s.Effects[x].LogicalKey == key {
			if s.Effects[x].IdempotencyKey == i.IdempotencyKey {
				return true, nil
			}
			s.Effects[x].Count++
			s.Effects = append(s.Effects, Effect{LogicalKey: key, IdempotencyKey: i.IdempotencyKey, Stage: i.Stage, ExecutionID: i.ExecutionID, BatchID: i.BatchID, ItemID: i.ItemID, Generation: i.Generation, Count: 1})
			return false, nil
		}
	}
	s.Effects = append(s.Effects, Effect{LogicalKey: key, IdempotencyKey: i.IdempotencyKey, Stage: i.Stage, ExecutionID: i.ExecutionID, BatchID: i.BatchID, ItemID: i.ItemID, Generation: i.Generation, Count: 1})
	return false, nil
}
func main() {
	if len(os.Args) < 2 {
		fmt.Fprintln(os.Stderr, "command required")
		os.Exit(2)
	}
	mu.Lock()
	defer mu.Unlock()
	if err := os.MkdirAll(root, 0o755); err != nil {
		panic(err)
	}
	lock, err := os.OpenFile(root+"/runtime.lock", os.O_CREATE|os.O_RDWR, 0o600)
	if err != nil {
		panic(err)
	}
	defer lock.Close()
	if err := syscall.Flock(int(lock.Fd()), syscall.LOCK_EX); err != nil {
		panic(err)
	}
	defer syscall.Flock(int(lock.Fd()), syscall.LOCK_UN)
	cmd := os.Args[1]
	if cmd == "reset" {
		_ = os.RemoveAll(root)
		s := initial()
		if err := save(s); err != nil {
			panic(err)
		}
		encode(map[string]any{"ok": true})
		return
	}
	s, err := load()
	if err != nil {
		panic(err)
	}
	switch cmd {
	case "now":
		encode(map[string]string{"now": s.Now})
	case "clock":
		if len(os.Args) < 4 {
			panic("clock set|advance value")
		}
		t, err := time.Parse(time.RFC3339, s.Now)
		if err != nil {
			panic(err)
		}
		if os.Args[2] == "set" {
			t, err = time.Parse(time.RFC3339, os.Args[3])
		} else {
			var d time.Duration
			d, err = time.ParseDuration(os.Args[3])
			t = t.Add(d)
		}
		if err != nil {
			panic(err)
		}
		s.Now = t.UTC().Format(time.RFC3339)
		must(save(s))
		encode(map[string]string{"now": s.Now})
	case "inject":
		if len(os.Args) < 3 {
			panic("inject point [count]")
		}
		n := 1
		if len(os.Args) > 3 {
			n, _ = strconv.Atoi(os.Args[3])
		}
		s.Failures[os.Args[2]] = n
		must(save(s))
		encode(map[string]any{"ok": true})
	case "clear-failures":
		s.Failures = map[string]int{}
		must(save(s))
		encode(map[string]any{"ok": true})
	case "deploy":
		var d Deployment
		must(decode(&d))
		if consume(&s, "CONTROL_PLANE") {
			must(save(s))
			encode(map[string]any{"ok": false, "class": "transient", "message": "control plane unavailable"})
			return
		}
		if d.Generation <= 0 || len(d.Stages) != 12 {
			encode(map[string]any{"ok": false, "class": "permanent", "message": "invalid deployment"})
			return
		}
		s.Deployments[strconv.Itoa(d.Generation)] = d
		if s.ActiveGeneration == 0 {
			s.ActiveGeneration = d.Generation
		}
		must(save(s))
		encode(map[string]any{"ok": true, "generation": d.Generation, "digest": d.Digest})
	case "invoke":
		var i Invocation
		must(decode(&i))
		d, ok := s.Deployments[strconv.Itoa(i.Generation)]
		if !ok {
			encode(InvocationResult{OK: false, Class: "permanent", Message: "generation not deployed"})
			return
		}
		if s.Drift[fmt.Sprintf("generation:%d", i.Generation)] {
			encode(InvocationResult{OK: false, Class: "transient", Message: "deployment drift"})
			return
		}
		st, ok := stageMap(d)[i.Stage]
		if !ok {
			encode(InvocationResult{OK: false, Class: "permanent", Message: "stage not deployed"})
			return
		}
		if st.Alias != "live" {
			encode(InvocationResult{OK: false, Class: "permanent", Message: "unversioned alias"})
			return
		}
		if epoch, exists := s.ExecutionEpochs[i.ExecutionID]; exists {
			if epoch != i.Epoch || s.ExecutionGenerations[i.ExecutionID] != i.Generation {
				encode(InvocationResult{OK: false, Class: "stale", Message: "stale execution generation"})
				return
			}
		} else {
			s.ExecutionEpochs[i.ExecutionID] = i.Epoch
			s.ExecutionGenerations[i.ExecutionID] = i.Generation
		}
		if consume(&s, "BEFORE_STAGE:"+i.Stage) || consume(&s, "TIMEOUT:"+i.Stage) {
			s.Invocations = append(s.Invocations, i)
			must(save(s))
			encode(InvocationResult{OK: false, Class: "transient", Message: "injected stage failure"})
			return
		}
		if i.Stage == "validate_inputs" && i.Metadata["poison"] == "true" {
			s.Invocations = append(s.Invocations, i)
			must(save(s))
			encode(InvocationResult{OK: false, Class: "permanent", Message: "poison item"})
			return
		}
		if i.Stage == "acquire_lock" {
			if prior := s.BatchExecutions[i.BatchID]; prior != "" && prior != i.ExecutionID {
				encode(InvocationResult{OK: false, Class: "conflict", Message: "batch already owned by another execution"})
				return
			}
			if owner := s.Locks[i.BatchID]; owner != "" && owner != i.ExecutionID {
				encode(InvocationResult{OK: false, Class: "busy", Message: "batch locked"})
				return
			}
			s.Locks[i.BatchID] = i.ExecutionID
			s.BatchExecutions[i.BatchID] = i.ExecutionID
		}
		if i.Stage == "release_lock" {
			if s.Locks[i.BatchID] == i.ExecutionID {
				delete(s.Locks, i.BatchID)
			}
		}
		dup, effErr := applyEffect(&s, i)
		if effErr != nil {
			encode(InvocationResult{OK: false, Class: "permanent", Message: effErr.Error()})
			return
		}
		s.Invocations = append(s.Invocations, i)
		lost := consume(&s, "AFTER_EFFECT:"+i.Stage)
		must(save(s))
		encode(InvocationResult{OK: !lost, Class: map[bool]string{true: "transient", false: ""}[lost], Message: map[bool]string{true: "response lost after commit", false: ""}[lost], LostResponse: lost, Duplicate: dup, Output: map[string]string{"stage": i.Stage, "execution_id": i.ExecutionID, "batch_id": i.BatchID, "item_id": i.ItemID, "generation": strconv.Itoa(i.Generation), "artifact_digest": i.Metadata["artifact_digest"]}})
	case "control":
		var c struct {
			Generation int    `json:"generation"`
			Writer     string `json:"writer"`
			Epoch      int64  `json:"epoch"`
		}
		must(decode(&c))
		if _, ok := s.Deployments[strconv.Itoa(c.Generation)]; !ok {
			encode(map[string]any{"ok": false, "message": "generation missing"})
			return
		}
		if consume(&s, "AFTER_ALIAS_SHIFT") {
			s.ActiveGeneration = c.Generation
			s.Epoch++
			must(save(s))
			encode(map[string]any{"ok": false, "class": "transient", "message": "response lost after alias shift", "epoch": s.Epoch})
			return
		}
		s.ActiveGeneration = c.Generation
		if c.Writer != "" {
			s.Writer = c.Writer
		}
		if c.Epoch > s.Epoch {
			s.Epoch = c.Epoch
		} else {
			s.Epoch++
		}
		must(save(s))
		encode(map[string]any{"ok": true, "generation": s.ActiveGeneration, "writer": s.Writer, "epoch": s.Epoch})
	case "jenkins-run":
		var r struct {
			BatchID string `json:"batch_id"`
			Write   bool   `json:"write"`
		}
		must(decode(&r))
		if r.Write && s.Writer == "jenkins" {
			s.JenkinsWrites++
			s.Effects = append(s.Effects, Effect{LogicalKey: r.BatchID + "/jenkins", IdempotencyKey: "jenkins/" + r.BatchID, Stage: "jenkins_publish", BatchID: r.BatchID, Count: 1})
		}
		must(save(s))
		encode(map[string]any{"ok": true, "writer": s.Writer, "wrote": r.Write && s.Writer == "jenkins"})
	case "drift":
		if len(os.Args) < 3 {
			panic("drift kind")
		}
		s.Drift[os.Args[2]] = true
		must(save(s))
		encode(map[string]any{"ok": true})
	case "clear-drift":
		s.Drift = map[string]bool{}
		must(save(s))
		encode(map[string]any{"ok": true})
	case "dlq":
		var v struct {
			BatchID string `json:"batch_id"`
			ItemID  string `json:"item_id"`
		}
		must(decode(&v))
		s.DLQ[v.BatchID] = append(s.DLQ[v.BatchID], v.ItemID)
		sort.Strings(s.DLQ[v.BatchID])
		must(save(s))
		encode(map[string]any{"ok": true})
	case "inspect":
		if len(os.Args) < 3 {
			panic("inspect section")
		}
		switch os.Args[2] {
		case "state":
			encode(s)
		case "effects":
			encode(s.Effects)
		case "deployments":
			encode(s.Deployments)
		case "invocations":
			encode(s.Invocations)
		case "dlq":
			encode(s.DLQ)
		default:
			panic("unknown inspect section")
		}
	case "hash":
		b, _ := io.ReadAll(os.Stdin)
		h := sha256.Sum256(b)
		encode(map[string]string{"sha256": hex.EncodeToString(h[:])})
	default:
		fmt.Fprintln(os.Stderr, "unknown command", cmd)
		os.Exit(2)
	}
}
func must(err error) {
	if err != nil {
		panic(err)
	}
}
func init() { _ = filepath.Separator; _ = strings.Builder{} }
