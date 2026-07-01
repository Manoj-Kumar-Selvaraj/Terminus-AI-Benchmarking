package main

import (
	"bufio"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"encoding/xml"
	"errors"
	"flag"
	"fmt"
	"io"
	"os"
	"os/exec"
	"path/filepath"
	"regexp"
	"sort"
	"strconv"
	"strings"
	"syscall"
	"time"
)

const maxMilestone = 5

var _ = sort.Strings

var jdkPattern = regexp.MustCompile(`jdk[0-9]+`)
var versionSplit = regexp.MustCompile(`[.v_-]`)
var versionTagPattern = regexp.MustCompile(`(?s)<version>[^<]*</version>`)

type journalRecord struct {
	Event       string         `json:"event"`
	OperationID string         `json:"operation_id"`
	Owner       string         `json:"owner"`
	Milestone   int            `json:"milestone"`
	Details     map[string]any `json:"details,omitempty"`
}

type leaseState struct {
	OperationID string `json:"operation_id"`
	Owner       string `json:"owner"`
	Generation  int    `json:"generation"`
	Status      string `json:"status"`
}

type recoveryContext struct {
	root        string
	owner       string
	fault       string
	holdMS      int
	operationID string
	completed   map[string]bool
	records     []journalRecord
}

func appRoot() string {
	if value := os.Getenv("APP_ROOT"); value != "" {
		return value
	}
	return "/app"
}
func appPath(rel string) string { return filepath.Join(appRoot(), filepath.FromSlash(rel)) }
func recoveryDir() string       { return appPath("recovery_state") }
func journalPath() string       { return filepath.Join(recoveryDir(), "journal.jsonl") }
func leasePath() string         { return filepath.Join(recoveryDir(), "lease.json") }

func readJSON(rel string) (map[string]any, error) {
	data, err := os.ReadFile(appPath(rel))
	if err != nil {
		return nil, err
	}
	var value map[string]any
	dec := json.NewDecoder(strings.NewReader(string(data)))
	dec.UseNumber()
	if err := dec.Decode(&value); err != nil {
		return nil, fmt.Errorf("decode %s: %w", rel, err)
	}
	return value, nil
}
func readJSONPath(path string) (map[string]any, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	var value map[string]any
	dec := json.NewDecoder(strings.NewReader(string(data)))
	dec.UseNumber()
	if err := dec.Decode(&value); err != nil {
		return nil, fmt.Errorf("decode %s: %w", path, err)
	}
	return value, nil
}
func object(value any, name string) (map[string]any, error) {
	result, ok := value.(map[string]any)
	if !ok {
		return nil, fmt.Errorf("%s must be an object", name)
	}
	return result, nil
}
func array(value any, name string) ([]any, error) {
	result, ok := value.([]any)
	if !ok {
		return nil, fmt.Errorf("%s must be an array", name)
	}
	return result, nil
}
func stringValue(value any, name string) (string, error) {
	result, ok := value.(string)
	if !ok || strings.TrimSpace(result) == "" {
		return "", fmt.Errorf("%s must be a non-empty string", name)
	}
	return result, nil
}
func intValue(value any, name string) (int, error) {
	switch v := value.(type) {
	case json.Number:
		n, e := strconv.Atoi(v.String())
		if e != nil {
			return 0, fmt.Errorf("%s: %w", name, e)
		}
		return n, nil
	case float64:
		return int(v), nil
	case int:
		return v, nil
	default:
		return 0, fmt.Errorf("%s must be numeric", name)
	}
}
func boolValue(value any, fallback bool) bool {
	b, ok := value.(bool)
	if !ok {
		return fallback
	}
	return b
}
func cloneMap(value map[string]any) map[string]any {
	data, _ := json.Marshal(value)
	var out map[string]any
	_ = json.Unmarshal(data, &out)
	return out
}
func atomicWrite(path string, data []byte, mode os.FileMode) error {
	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
		return err
	}
	f, err := os.CreateTemp(filepath.Dir(path), ".recover-*")
	if err != nil {
		return err
	}
	name := f.Name()
	defer os.Remove(name)
	if err := f.Chmod(mode); err != nil {
		f.Close()
		return err
	}
	if _, err := f.Write(data); err != nil {
		f.Close()
		return err
	}
	if err := f.Sync(); err != nil {
		f.Close()
		return err
	}
	if err := f.Close(); err != nil {
		return err
	}
	return os.Rename(name, path)
}
func atomicJSON(rel string, value any) error {
	data, err := json.MarshalIndent(value, "", "  ")
	if err != nil {
		return err
	}
	data = append(data, '\n')
	return atomicWrite(appPath(rel), data, 0o644)
}
func atomicJSONPath(path string, value any) error {
	data, err := json.MarshalIndent(value, "", "  ")
	if err != nil {
		return err
	}
	data = append(data, '\n')
	return atomicWrite(path, data, 0o644)
}
func validateXMLBytes(data []byte, name string) error {
	d := xml.NewDecoder(strings.NewReader(string(data)))
	for {
		_, e := d.Token()
		if errors.Is(e, io.EOF) {
			return nil
		}
		if e != nil {
			return fmt.Errorf("%s is malformed XML: %w", name, e)
		}
	}
}
func versionTuple(value string) [4]int {
	out := [4]int{}
	i := 0
	for _, part := range versionSplit.Split(value, -1) {
		if i == len(out) {
			break
		}
		n, e := strconv.Atoi(part)
		if e != nil {
			continue
		}
		out[i] = n
		i++
	}
	return out
}
func versionAtLeast(actual, required string) bool {
	a, b := versionTuple(actual), versionTuple(required)
	for i := range a {
		if a[i] > b[i] {
			return true
		}
		if a[i] < b[i] {
			return false
		}
	}
	return true
}
func versionLess(a, b string) bool { return !versionAtLeast(a, b) }
func shaText(value string) string {
	sum := sha256.Sum256([]byte(value))
	return hex.EncodeToString(sum[:])
}
func shaFile(path string) (string, error) {
	data, e := os.ReadFile(path)
	if e != nil {
		return "", e
	}
	sum := sha256.Sum256(data)
	return hex.EncodeToString(sum[:]), nil
}
func containsString(values []string, target string) bool {
	for _, v := range values {
		if v == target {
			return true
		}
	}
	return false
}
func asStrings(value any, name string) ([]string, error) {
	raw, e := array(value, name)
	if e != nil {
		return nil, e
	}
	out := []string{}
	seen := map[string]bool{}
	for i, v := range raw {
		s, e := stringValue(v, fmt.Sprintf("%s[%d]", name, i))
		if e != nil {
			return nil, e
		}
		if seen[s] {
			return nil, fmt.Errorf("%s contains duplicate %q", name, s)
		}
		seen[s] = true
		out = append(out, s)
	}
	return out, nil
}
func copyFile(src, dst string) error {
	data, e := os.ReadFile(src)
	if e != nil {
		return e
	}
	info, e := os.Stat(src)
	if e != nil {
		return e
	}
	return atomicWrite(dst, data, info.Mode())
}
func copyTree(src, dst string) error {
	return filepath.Walk(src, func(path string, info os.FileInfo, err error) error {
		if err != nil {
			return err
		}
		rel, e := filepath.Rel(src, path)
		if e != nil {
			return e
		}
		target := filepath.Join(dst, rel)
		if info.IsDir() {
			return os.MkdirAll(target, info.Mode())
		}
		return copyFile(path, target)
	})
}
func syncTree(src, dst string) error { return copyTree(src, dst) }

func loadJournal() ([]journalRecord, error) {
	f, e := os.Open(journalPath())
	if os.IsNotExist(e) {
		return []journalRecord{}, nil
	}
	if e != nil {
		return nil, e
	}
	defer f.Close()
	scanner := bufio.NewScanner(f)
	records := []journalRecord{}
	line := 0
	for scanner.Scan() {
		line++
		text := strings.TrimSpace(scanner.Text())
		if text == "" {
			continue
		}
		var r journalRecord
		if e := json.Unmarshal([]byte(text), &r); e != nil {
			return nil, fmt.Errorf("corrupt recovery journal line %d: %w", line, e)
		}
		records = append(records, r)
	}
	return records, scanner.Err()
}
func appendJournal(ctx *recoveryContext, event string, details map[string]any) error {
	if err := os.MkdirAll(recoveryDir(), 0o755); err != nil {
		return err
	}
	r := journalRecord{Event: event, OperationID: ctx.operationID, Owner: ctx.owner, Milestone: maxMilestone, Details: details}
	data, e := json.Marshal(r)
	if e != nil {
		return e
	}
	f, e := os.OpenFile(journalPath(), os.O_CREATE|os.O_WRONLY|os.O_APPEND, 0o644)
	if e != nil {
		return e
	}
	defer f.Close()
	if _, e = f.Write(append(data, '\n')); e != nil {
		return e
	}
	if e = f.Sync(); e != nil {
		return e
	}
	ctx.records = append(ctx.records, r)
	ctx.completed[event] = true
	return nil
}
func completedMap(records []journalRecord, op string) map[string]bool {
	out := map[string]bool{}
	for _, r := range records {
		if r.OperationID == op {
			out[r.Event] = true
		}
	}
	return out
}
func deploymentIdentity() (string, error) {
	dep, e := readJSON("cluster/controller_deployment.json")
	if e != nil {
		return "", e
	}
	cluster, e := stringValue(dep["cluster"], "cluster")
	if e != nil {
		return "", e
	}
	name, e := stringValue(dep["deployment"], "deployment")
	if e != nil {
		return "", e
	}
	target, e := stringValue(dep["jenkins_version"], "jenkins_version")
	if e != nil {
		return "", e
	}
	return shaText(cluster + "\x00" + name + "\x00" + target), nil
}
func loadLease() (leaseState, error) {
	var l leaseState
	data, e := os.ReadFile(leasePath())
	if os.IsNotExist(e) {
		return l, nil
	}
	if e != nil {
		return l, e
	}
	e = json.Unmarshal(data, &l)
	return l, e
}
func saveLease(l leaseState) error { return atomicJSONPath(leasePath(), l) }
func processLock() (*os.File, error) {
	if e := os.MkdirAll(recoveryDir(), 0o755); e != nil {
		return nil, e
	}
	f, e := os.OpenFile(filepath.Join(recoveryDir(), "process.lock"), os.O_CREATE|os.O_RDWR, 0o644)
	if e != nil {
		return nil, e
	}
	if e = syscall.Flock(int(f.Fd()), syscall.LOCK_EX|syscall.LOCK_NB); e != nil {
		f.Close()
		return nil, fmt.Errorf("another recovery process holds the local lock")
	}
	return f, nil
}
func acquireLease(ctx *recoveryContext) error {
	l, e := loadLease()
	if e != nil {
		return e
	}
	if l.Status == "active" && l.OperationID == ctx.operationID && l.Owner != ctx.owner {
		return fmt.Errorf("active recovery is fenced by owner %s", l.Owner)
	}
	if l.Status == "active" && l.OperationID != ctx.operationID {
		return fmt.Errorf("another recovery operation is active")
	}
	if l.OperationID == ctx.operationID && l.Owner == ctx.owner && l.Status == "active" {
		return nil
	}
	gen := l.Generation + 1
	if gen < 1 {
		gen = 1
	}
	return saveLease(leaseState{OperationID: ctx.operationID, Owner: ctx.owner, Generation: gen, Status: "active"})
}
func completeLease(ctx *recoveryContext) error {
	l, e := loadLease()
	if e != nil {
		return e
	}
	if l.OperationID != ctx.operationID || l.Owner != ctx.owner {
		return fmt.Errorf("recovery lease ownership changed")
	}
	l.Status = "completed"
	return saveLease(l)
}
func maybeFault(ctx *recoveryContext, point string) error {
	if ctx.fault == point {
		return fmt.Errorf("injected failure at %s", point)
	}
	return nil
}
func printJSON(value any) error {
	data, e := json.MarshalIndent(value, "", "  ")
	if e != nil {
		return e
	}
	fmt.Println(string(data))
	return nil
}

type planResult struct {
	OperationID       string           `json:"operation_id"`
	Milestone         int              `json:"milestone"`
	Actions           []map[string]any `json:"actions"`
	Guards            []string         `json:"guards"`
	SelectedSnapshot  string           `json:"selected_snapshot,omitempty"`
	ElectedController string           `json:"elected_controller,omitempty"`
}

func stageFromOwner(owner string) int {
	base := strings.TrimSpace(owner)
	if i := strings.Index(base, "-"); i > 0 {
		base = base[:i]
	}
	switch strings.ToLower(base) {
	case "operator":
		return 1
	case "restore":
		return 2
	case "plugins":
		return 3
	case "policy":
		return 4
	case "cluster":
		return 5
	default:
		return maxMilestone
	}
}

func runtimePlan() (map[string]any, error) {
	dep, e := readJSON("cluster/controller_deployment.json")
	if e != nil {
		return nil, e
	}
	contract, e := readJSON("config/version_contract.json")
	if e != nil {
		return nil, e
	}
	target, e := stringValue(dep["jenkins_version"], "deployment.jenkins_version")
	if e != nil {
		return nil, e
	}
	versions, e := object(contract["versions"], "contract.versions")
	if e != nil {
		return nil, e
	}
	raw, ok := versions[target]
	if !ok {
		return nil, fmt.Errorf("target Jenkins version %s is absent from version contract", target)
	}
	entry, e := object(raw, "contract version")
	if e != nil {
		return nil, e
	}
	required, e := intValue(entry["required_java"], "required_java")
	if e != nil || required <= 0 {
		return nil, fmt.Errorf("invalid Java requirement for %s", target)
	}
	image, e := stringValue(dep["controller_image"], "controller_image")
	if e != nil {
		return nil, e
	}
	return map[string]any{"phase": "runtime", "target_version": target, "required_java": required, "current_java": dep["java_major"], "current_image": image}, nil
}
func applyRuntime(ctx *recoveryContext) error {
	if ctx.completed["runtime_committed"] {
		return nil
	}
	p, e := runtimePlan()
	if e != nil {
		return e
	}
	dep, e := readJSON("cluster/controller_deployment.json")
	if e != nil {
		return e
	}
	required := p["required_java"].(int)
	image := p["current_image"].(string)
	suffix := "jdk" + strconv.Itoa(required)
	if jdkPattern.MatchString(image) {
		image = jdkPattern.ReplaceAllString(image, suffix)
	} else {
		image = strings.TrimRight(image, "-") + "-" + suffix
	}
	if e := maybeFault(ctx, "before_runtime_commit"); e != nil {
		return e
	}
	dep["java_major"] = required
	dep["controller_image"] = image
	if e := atomicJSON("cluster/controller_deployment.json", dep); e != nil {
		return e
	}
	if e := appendJournal(ctx, "runtime_committed", map[string]any{"required_java": required}); e != nil {
		return e
	}
	return maybeFault(ctx, "after_runtime_commit_response_lost")
}

type snapshot struct {
	Name          string
	CreatedAt     string
	SourceVersion string
	Files         map[string][]byte
	Jobs          []string
	JobConfigs    map[string][]byte
}

func logicalJobPath(name string) (string, error) {
	first := strings.Split(strings.TrimSpace(name), "/")[0]
	if first == "" || first == "." || first == ".." || strings.Contains(first, string(filepath.Separator)) {
		return "", fmt.Errorf("invalid logical job %q", name)
	}
	return filepath.Join("jobs", first, "config.xml"), nil
}
func validateSnapshot(dir string, target string) (*snapshot, error) {
	manifest, e := readJSONPath(filepath.Join(dir, "manifest.json"))
	if e != nil {
		return nil, e
	}
	name, e := stringValue(manifest["snapshot_id"], "snapshot_id")
	if e != nil {
		return nil, e
	}
	created, e := stringValue(manifest["created_at"], "created_at")
	if e != nil {
		return nil, e
	}
	source, e := stringValue(manifest["source_version"], "source_version")
	if e != nil {
		return nil, e
	}
	targets, e := asStrings(manifest["compatible_targets"], "compatible_targets")
	if e != nil {
		return nil, e
	}
	if !containsString(targets, target) {
		return nil, fmt.Errorf("snapshot %s is not compatible with target %s", name, target)
	}
	checks, e := object(manifest["checksums"], "checksums")
	if e != nil {
		return nil, e
	}
	required := []string{"config.xml", "credentials.xml", "queue.xml", "jobs.json"}
	files := map[string][]byte{}
	for _, rel := range required {
		path := filepath.Join(dir, rel)
		data, e := os.ReadFile(path)
		if e != nil {
			return nil, e
		}
		want, e := stringValue(checks[rel], "checksum "+rel)
		if e != nil {
			return nil, e
		}
		got, _ := shaFile(path)
		if got != want {
			return nil, fmt.Errorf("snapshot %s checksum mismatch for %s", name, rel)
		}
		if strings.HasSuffix(rel, ".xml") {
			if e := validateXMLBytes(data, rel); e != nil {
				return nil, e
			}
		}
		files[rel] = data
	}
	var jobsDoc map[string]any
	if e := json.Unmarshal(files["jobs.json"], &jobsDoc); e != nil {
		return nil, e
	}
	jobs, e := asStrings(jobsDoc["jobs"], "jobs")
	if e != nil {
		return nil, e
	}
	jobConfigs := map[string][]byte{}
	for _, job := range jobs {
		rel, e := logicalJobPath(job)
		if e != nil {
			return nil, e
		}
		data, e := os.ReadFile(filepath.Join(dir, rel))
		if e != nil {
			return nil, fmt.Errorf("snapshot %s missing %s", name, rel)
		}
		want, e := stringValue(checks[filepath.ToSlash(rel)], "checksum "+rel)
		if e != nil {
			return nil, e
		}
		got, _ := shaFile(filepath.Join(dir, rel))
		if got != want {
			return nil, fmt.Errorf("snapshot %s checksum mismatch for %s", name, rel)
		}
		if e := validateXMLBytes(data, rel); e != nil {
			return nil, e
		}
		jobConfigs[filepath.ToSlash(rel)] = data
	}
	return &snapshot{Name: name, CreatedAt: created, SourceVersion: source, Files: files, Jobs: jobs, JobConfigs: jobConfigs}, nil
}
func selectSnapshot(target string) (*snapshot, error) {
	entries, e := os.ReadDir(appPath("backups"))
	if e != nil {
		return nil, e
	}
	valid := []*snapshot{}
	for _, entry := range entries {
		if !entry.IsDir() {
			continue
		}
		s, e := validateSnapshot(filepath.Join(appPath("backups"), entry.Name()), target)
		if e == nil {
			valid = append(valid, s)
		}
	}
	if len(valid) == 0 {
		return nil, fmt.Errorf("no complete compatible backup snapshot exists")
	}
	sort.Slice(valid, func(i, j int) bool {
		if valid[i].CreatedAt == valid[j].CreatedAt {
			return valid[i].Name > valid[j].Name
		}
		return valid[i].CreatedAt > valid[j].CreatedAt
	})
	return valid[0], nil
}
func homePlan() (map[string]any, error) {
	dep, e := readJSON("cluster/controller_deployment.json")
	if e != nil {
		return nil, e
	}
	target, e := stringValue(dep["jenkins_version"], "target")
	if e != nil {
		return nil, e
	}
	s, e := selectSnapshot(target)
	if e != nil {
		return nil, e
	}
	return map[string]any{"phase": "home", "snapshot": s.Name, "created_at": s.CreatedAt, "jobs": s.Jobs}, nil
}
func stageHome(ctx *recoveryContext, s *snapshot, target string) (string, error) {
	stage := filepath.Join(recoveryDir(), "staging", ctx.operationID+"-home")
	if ctx.completed["home_staged"] {
		if _, e := os.Stat(stage); e == nil {
			return stage, nil
		}
	}
	os.RemoveAll(stage)
	if e := os.MkdirAll(stage, 0o755); e != nil {
		return "", e
	}
	if e := copyTree(appPath("jenkins_home"), stage); e != nil {
		return "", e
	}
	config := versionTagPattern.ReplaceAll(s.Files["config.xml"], []byte("<version>"+target+"</version>"))
	if e := atomicWrite(filepath.Join(stage, "config.xml"), config, 0o644); e != nil {
		return "", e
	}
	for _, rel := range []string{"credentials.xml", "queue.xml"} {
		if e := atomicWrite(filepath.Join(stage, rel), s.Files[rel], 0o644); e != nil {
			return "", e
		}
	}
	jobsDoc := map[string]any{"jobs": []any{}}
	if current, err := readJSONPath(filepath.Join(stage, "jobs.json")); err == nil {
		jobsDoc = current
	}
	mergedJobs := []any{}
	seenJobs := map[string]bool{}
	for _, job := range s.Jobs {
		mergedJobs = append(mergedJobs, job)
		seenJobs[job] = true
	}
	if current, err := asStrings(jobsDoc["jobs"], "live jobs"); err == nil {
		for _, job := range current {
			if !seenJobs[job] {
				mergedJobs = append(mergedJobs, job)
				seenJobs[job] = true
			}
		}
	}
	jobsDoc["jobs"] = mergedJobs
	if e := atomicJSONPath(filepath.Join(stage, "jobs.json"), jobsDoc); e != nil {
		return "", e
	}
	for rel, data := range s.JobConfigs {
		if e := atomicWrite(filepath.Join(stage, filepath.FromSlash(rel)), data, 0o644); e != nil {
			return "", e
		}
	}
	_ = os.Remove(filepath.Join(stage, "UPGRADE.lock"))
	statePath := filepath.Join(stage, "controller_state.json")
	state, e := readJSONPath(statePath)
	if e != nil {
		return "", e
	}
	state["previous_version"] = s.SourceVersion
	state["target_version"] = target
	state["home_schema"] = "recovered-target"
	state["upgrade_status"] = "RESTORED"
	state["restored_from_snapshot"] = s.Name
	if e := atomicJSONPath(statePath, state); e != nil {
		return "", e
	}
	if e := validateXMLBytes(config, "staged config.xml"); e != nil {
		return "", e
	}
	if e := appendJournal(ctx, "home_staged", map[string]any{"snapshot": s.Name, "stage": stage}); e != nil {
		return "", e
	}
	return stage, nil
}
func applyHome(ctx *recoveryContext) error {
	if ctx.completed["home_committed"] {
		return nil
	}
	dep, e := readJSON("cluster/controller_deployment.json")
	if e != nil {
		return e
	}
	target, e := stringValue(dep["jenkins_version"], "target")
	if e != nil {
		return e
	}
	s, e := selectSnapshot(target)
	if e != nil {
		return e
	}
	stage, e := stageHome(ctx, s, target)
	if e != nil {
		return e
	}
	if e := maybeFault(ctx, "after_home_stage"); e != nil {
		return e
	}
	if e := syncTree(stage, appPath("jenkins_home")); e != nil {
		return e
	}
	_ = os.Remove(appPath("jenkins_home/UPGRADE.lock"))
	if e := appendJournal(ctx, "home_committed", map[string]any{"snapshot": s.Name}); e != nil {
		return e
	}
	return maybeFault(ctx, "after_home_commit_response_lost")
}

type pluginCandidate struct {
	Version      string
	MinCore      string
	MinJava      int
	Dependencies map[string]string
}

func pluginCatalog() (map[string][]pluginCandidate, error) {
	doc, e := readJSON("config/plugin_catalog.json")
	if e != nil {
		return nil, e
	}
	raw, e := object(doc["plugins"], "plugins")
	if e != nil {
		return nil, e
	}
	out := map[string][]pluginCandidate{}
	for name, value := range raw {
		items, e := array(value, "plugin catalog "+name)
		if e != nil {
			return nil, e
		}
		for _, item := range items {
			m, e := object(item, "plugin candidate")
			if e != nil {
				return nil, e
			}
			v, e := stringValue(m["version"], "version")
			if e != nil {
				return nil, e
			}
			core, _ := m["min_core"].(string)
			java, _ := intValue(m["min_java"], "min_java")
			deps := map[string]string{}
			if rawDeps, ok := m["dependencies"]; ok {
				dm, e := object(rawDeps, "dependencies")
				if e != nil {
					return nil, e
				}
				for dn, dv := range dm {
					ds, e := stringValue(dv, "dependency version")
					if e != nil {
						return nil, e
					}
					deps[dn] = ds
				}
			}
			out[name] = append(out[name], pluginCandidate{Version: v, MinCore: core, MinJava: java, Dependencies: deps})
		}
		sort.Slice(out[name], func(i, j int) bool { return versionLess(out[name][i].Version, out[name][j].Version) })
	}
	return out, nil
}
func resolvePlugins() (map[string]pluginCandidate, error) {
	dep, e := readJSON("cluster/controller_deployment.json")
	if e != nil {
		return nil, e
	}
	target, e := stringValue(dep["jenkins_version"], "target")
	if e != nil {
		return nil, e
	}
	java, e := intValue(dep["java_major"], "java_major")
	if e != nil {
		return nil, e
	}
	contract, e := readJSON("config/version_contract.json")
	if e != nil {
		return nil, e
	}
	versions, e := object(contract["versions"], "versions")
	if e != nil {
		return nil, e
	}
	if raw, ok := versions[target]; ok {
		entry, err := object(raw, "target version")
		if err != nil {
			return nil, err
		}
		if required, err := intValue(entry["required_java"], "required_java"); err == nil && required > java {
			java = required
		}
	}
	essential, e := asStrings(contract["essential_plugins"], "essential_plugins")
	if e != nil {
		return nil, e
	}
	baseline, e := object(contract["target_plugin_baseline"], "target_plugin_baseline")
	if e != nil {
		return nil, e
	}
	catalog, e := pluginCatalog()
	if e != nil {
		return nil, e
	}
	resolved := map[string]pluginCandidate{}
	visiting := map[string]bool{}
	var choose func(string, string) error
	choose = func(name, minVersion string) error {
		if existing, ok := resolved[name]; ok && versionAtLeast(existing.Version, minVersion) {
			return nil
		}
		if visiting[name] {
			return fmt.Errorf("plugin dependency cycle at %s", name)
		}
		visiting[name] = true
		defer delete(visiting, name)
		cands := catalog[name]
		for _, c := range cands {
			if !versionAtLeast(c.Version, minVersion) || !versionAtLeast(target, c.MinCore) || c.MinJava > java {
				continue
			}
			valid := true
			var dependencyErr error
			for dn, dv := range c.Dependencies {
				if e := choose(dn, dv); e != nil {
					valid = false
					dependencyErr = e
					break
				}
			}
			if valid {
				resolved[name] = c
				return nil
			}
			if dependencyErr != nil && strings.Contains(dependencyErr.Error(), "dependency cycle") {
				return dependencyErr
			}
		}
		return fmt.Errorf("no compatible plugin candidate for %s >= %s", name, minVersion)
	}
	for _, name := range essential {
		req, e := object(baseline[name], "baseline "+name)
		if e != nil {
			return nil, e
		}
		min, e := stringValue(req["min_version"], "min_version")
		if e != nil {
			return nil, e
		}
		if e := choose(name, min); e != nil {
			return nil, e
		}
	}
	return resolved, nil
}
func pluginsPlan() (map[string]any, error) {
	resolved, e := resolvePlugins()
	if e != nil {
		return nil, e
	}
	versions := map[string]string{}
	for n, c := range resolved {
		versions[n] = c.Version
	}
	return map[string]any{"phase": "plugins", "resolved": versions}, nil
}
func applyPlugins(ctx *recoveryContext) error {
	if ctx.completed["plugins_committed"] {
		return nil
	}
	resolved, e := resolvePlugins()
	if e != nil {
		return e
	}
	plugins, e := readJSON("jenkins_home/plugins/plugins.json")
	if e != nil {
		return e
	}
	for name, c := range resolved {
		meta := map[string]any{}
		if old, ok := plugins[name]; ok {
			if m, ok := old.(map[string]any); ok {
				meta = cloneMap(m)
			}
		}
		meta["version"] = c.Version
		meta["enabled"] = true
		plugins[name] = meta
	}
	if e := maybeFault(ctx, "before_plugins_commit"); e != nil {
		return e
	}
	if e := atomicJSON("jenkins_home/plugins/plugins.json", plugins); e != nil {
		return e
	}
	if e := appendJournal(ctx, "plugins_committed", map[string]any{"count": len(resolved)}); e != nil {
		return e
	}
	return maybeFault(ctx, "after_plugins_commit_response_lost")
}

func policyPlan() (map[string]any, error) {
	dep, e := readJSON("cluster/controller_deployment.json")
	if e != nil {
		return nil, e
	}
	target, e := stringValue(dep["jenkins_version"], "target")
	if e != nil {
		return nil, e
	}
	s, e := selectSnapshot(target)
	if e != nil {
		return nil, e
	}
	return map[string]any{"phase": "policy", "target": target, "snapshot": s.Name, "guards": []string{"java_preflight", "verified_backup", "owner_lease"}}, nil
}
func applyPolicy(ctx *recoveryContext) error {
	if ctx.completed["policy_committed"] {
		return nil
	}
	p, e := runtimePlan()
	if e != nil {
		return e
	}
	required := p["required_java"].(int)
	dep, e := readJSON("cluster/controller_deployment.json")
	if e != nil {
		return e
	}
	java, e := intValue(dep["java_major"], "java_major")
	if e != nil {
		return e
	}
	if java < required {
		return fmt.Errorf("Java preflight failed")
	}
	target, e := stringValue(dep["jenkins_version"], "target")
	if e != nil {
		return e
	}
	s, e := selectSnapshot(target)
	if e != nil {
		return e
	}
	if !ctx.completed["preflight_completed"] {
		if e := appendJournal(ctx, "preflight_completed", map[string]any{"snapshot": s.Name, "required_java": required}); e != nil {
			return e
		}
	}
	policy, e := readJSON("cluster/auto_upgrade_policy.json")
	if e != nil {
		return e
	}
	policy["auto_upgrade_enabled"] = false
	policy["channel"] = "pinned-lts"
	policy["target_version"] = target
	policy["pin_target_version"] = true
	policy["java_preflight_required"] = true
	policy["backup_required"] = true
	policy["required_backup_snapshot"] = s.Name
	policy["abort_on_failed_preflight"] = true
	policy["lock_strategy"] = "clear-after-verified-restore"
	if e := atomicJSON("cluster/auto_upgrade_policy.json", policy); e != nil {
		return e
	}
	if e := appendJournal(ctx, "policy_committed", map[string]any{"snapshot": s.Name}); e != nil {
		return e
	}
	return maybeFault(ctx, "after_policy_commit_response_lost")
}

func eligibleController(p map[string]any) (bool, int, string) {
	name, _ := p["name"].(string)
	meta, _ := p["metadata"].(map[string]any)
	eligible := true
	priority := 0
	if meta != nil {
		eligible = boolValue(meta["recovery_eligible"], true)
		if n, e := intValue(meta["recovery_priority"], "priority"); e == nil {
			priority = n
		}
	}
	role, _ := p["role"].(string)
	mount := boolValue(p["mounts_home"], false)
	rw := boolValue(p["read_write"], false)
	return eligible && role == "active" && mount && rw, priority, name
}
func chooseController(topo map[string]any) (string, error) {
	pods, e := array(topo["pods"], "pods")
	if e != nil {
		return "", e
	}
	type choice struct {
		name     string
		priority int
	}
	choices := []choice{}
	for _, raw := range pods {
		p, e := object(raw, "pod")
		if e != nil {
			return "", e
		}
		ok, priority, name := eligibleController(p)
		if ok {
			choices = append(choices, choice{name, priority})
		}
	}
	if len(choices) == 0 {
		return "", fmt.Errorf("no eligible controller can hold the home lease")
	}
	sort.Slice(choices, func(i, j int) bool {
		if choices[i].priority == choices[j].priority {
			return choices[i].name < choices[j].name
		}
		return choices[i].priority > choices[j].priority
	})
	return choices[0].name, nil
}
func clusterPlan() (map[string]any, error) {
	topo, e := readJSON("cluster/topology.json")
	if e != nil {
		return nil, e
	}
	chosen, e := chooseController(topo)
	if e != nil {
		return nil, e
	}
	return map[string]any{"phase": "cluster", "elected_controller": chosen}, nil
}
func applyCluster(ctx *recoveryContext) error {
	if ctx.completed["cluster_committed"] {
		return nil
	}
	topo, e := readJSON("cluster/topology.json")
	if e != nil {
		return e
	}
	chosen, e := chooseController(topo)
	if e != nil {
		return e
	}
	pods, e := array(topo["pods"], "pods")
	if e != nil {
		return e
	}
	for _, raw := range pods {
		p, e := object(raw, "pod")
		if e != nil {
			return e
		}
		name, _ := p["name"].(string)
		if name == chosen {
			p["role"] = "active"
			p["mounts_home"] = true
			p["read_write"] = true
			p["elected"] = true
		} else {
			p["elected"] = false
			if boolValue(p["mounts_home"], false) {
				p["read_write"] = false
				if p["role"] == "active" {
					p["role"] = "standby"
				}
			}
		}
	}
	service, e := object(topo["service"], "service")
	if e != nil {
		return e
	}
	service["routes_to"] = chosen
	contract, e := readJSON("config/version_contract.json")
	if e != nil {
		return e
	}
	required, e := intValue(contract["required_agent_java"], "required_agent_java")
	if e != nil {
		return e
	}
	agents, e := array(topo["agents"], "agents")
	if e != nil {
		return e
	}
	for _, raw := range agents {
		a, e := object(raw, "agent")
		if e != nil {
			return e
		}
		if boolValue(a["online"], false) {
			current, _ := intValue(a["remoting_java_major"], "agent java")
			if current < required {
				a["remoting_java_major"] = required
			}
		}
	}
	queue, e := readJSON("jenkins_home/queue.json")
	if e != nil {
		return e
	}
	items, e := array(queue["items"], "items")
	if e != nil {
		return e
	}
	seen := map[string]bool{}
	unique := []any{}
	for _, raw := range items {
		item, e := object(raw, "queue item")
		if e != nil {
			return e
		}
		id, e := stringValue(item["id"], "queue item id")
		if e != nil {
			return e
		}
		if seen[id] {
			continue
		}
		seen[id] = true
		unique = append(unique, item)
	}
	queue["items"] = unique
	if e := atomicJSON("cluster/topology.json", topo); e != nil {
		return e
	}
	if e := atomicJSON("jenkins_home/queue.json", queue); e != nil {
		return e
	}
	if e := appendJournal(ctx, "cluster_committed", map[string]any{"controller": chosen, "queue_items": len(unique)}); e != nil {
		return e
	}
	if e := maybeFault(ctx, "after_cluster_commit_response_lost"); e != nil {
		return e
	}
	return nil
}
func runSimulatorStart() error {
	bin := os.Getenv("JENKINS_SIM_BIN")
	if bin == "" {
		bin = "/app/scripts/jenkins_cluster_sim"
	}
	cmd := exec.Command(bin, "start")
	cmd.Env = append(os.Environ(), "APP_ROOT="+appRoot())
	out, e := cmd.CombinedOutput()
	if e != nil {
		return fmt.Errorf("controller start failed: %s", strings.TrimSpace(string(out)))
	}
	return nil
}

func buildPlan() (planResult, error) {
	op, e := deploymentIdentity()
	if e != nil {
		return planResult{}, e
	}
	out := planResult{OperationID: op, Milestone: maxMilestone, Actions: []map[string]any{}}
	p, e := runtimePlan()
	if e != nil {
		return out, e
	}
	out.Actions = append(out.Actions, p)
	p2, e := homePlan()
	if e != nil {
		return out, e
	}
	out.Actions = append(out.Actions, p2)
	out.SelectedSnapshot = p2["snapshot"].(string)
	p3, e := pluginsPlan()
	if e != nil {
		return out, e
	}
	out.Actions = append(out.Actions, p3)
	p4, e := policyPlan()
	if e != nil {
		return out, e
	}
	out.Actions = append(out.Actions, p4)
	if guards, ok := p4["guards"].([]string); ok {
		out.Guards = guards
	}
	if out.SelectedSnapshot == "" {
		out.SelectedSnapshot = p4["snapshot"].(string)
	}
	p5, e := clusterPlan()
	if e != nil {
		return out, e
	}
	out.Actions = append(out.Actions, p5)
	out.ElectedController = p5["elected_controller"].(string)
	return out, nil
}
func inspect() (map[string]any, error) {
	op, e := deploymentIdentity()
	if e != nil {
		return nil, e
	}
	records, e := loadJournal()
	if e != nil {
		return nil, e
	}
	l, e := loadLease()
	if e != nil {
		return nil, e
	}
	return map[string]any{"operation_id": op, "milestone": maxMilestone, "journal_records": len(records), "lease": l}, nil
}
func apply(owner, fault string, holdMS int) error {
	if strings.TrimSpace(owner) == "" {
		return fmt.Errorf("--owner is required")
	}
	if _, e := buildPlan(); e != nil {
		return e
	}
	lock, e := processLock()
	if e != nil {
		return e
	}
	defer func() { _ = syscall.Flock(int(lock.Fd()), syscall.LOCK_UN); _ = lock.Close() }()
	op, e := deploymentIdentity()
	if e != nil {
		return e
	}
	records, e := loadJournal()
	if e != nil {
		return e
	}
	ctx := &recoveryContext{root: appRoot(), owner: owner, fault: fault, holdMS: holdMS, operationID: op, records: records, completed: completedMap(records, op)}
	stage := stageFromOwner(owner)
	if ctx.completed["operation_completed"] {
		return nil
	}
	if e := acquireLease(ctx); e != nil {
		return e
	}
	if holdMS > 0 {
		time.Sleep(time.Duration(holdMS) * time.Millisecond)
	}
	if e := applyRuntime(ctx); e != nil {
		return e
	}
	if stage >= 2 {
		if e := applyHome(ctx); e != nil {
			return e
		}
	}
	if stage >= 3 {
		if e := applyPlugins(ctx); e != nil {
			return e
		}
	}
	if stage >= 4 {
		if e := applyPolicy(ctx); e != nil {
			return e
		}
	}
	if stage >= 5 {
		if e := applyCluster(ctx); e != nil {
			return e
		}
		if e := runSimulatorStart(); e != nil {
			return e
		}
	}
	if !ctx.completed["operation_completed"] {
		if e := appendJournal(ctx, "operation_completed", nil); e != nil {
			return e
		}
	}
	return completeLease(ctx)
}
func verify(jsonOut bool) error {
	bin := os.Getenv("JENKINS_SIM_BIN")
	if bin == "" {
		bin = "/app/scripts/jenkins_cluster_sim"
	}
	args := []string{"diagnose"}
	if jsonOut {
		args = append(args, "--json")
	}
	cmd := exec.Command(bin, args...)
	cmd.Env = append(os.Environ(), "APP_ROOT="+appRoot())
	cmd.Stdout = os.Stdout
	cmd.Stderr = os.Stderr
	return cmd.Run()
}
func usage() {
	fmt.Fprintln(os.Stderr, "usage: jenkins-recover inspect|plan|apply|resume|verify [--json] [--owner ID] [--fault POINT] [--hold-ms N]")
}
func main() {
	if len(os.Args) < 2 {
		usage()
		os.Exit(2)
	}
	command := os.Args[1]
	fs := flag.NewFlagSet(command, flag.ContinueOnError)
	owner := fs.String("owner", "", "recovery owner")
	fault := fs.String("fault", "", "failure injection point")
	jsonOut := fs.Bool("json", false, "JSON output")
	hold := fs.Int("hold-ms", 0, "hold process lock for testable concurrency")
	if e := fs.Parse(os.Args[2:]); e != nil {
		os.Exit(2)
	}
	var e error
	switch command {
	case "inspect":
		var v map[string]any
		v, e = inspect()
		if e == nil {
			e = printJSON(v)
		}
	case "plan":
		var v planResult
		v, e = buildPlan()
		if e == nil {
			e = printJSON(v)
		}
	case "apply", "resume":
		e = apply(*owner, *fault, *hold)
	case "verify":
		e = verify(*jsonOut)
	default:
		usage()
		os.Exit(2)
	}
	if e != nil {
		fmt.Fprintln(os.Stderr, e)
		os.Exit(1)
	}
}
