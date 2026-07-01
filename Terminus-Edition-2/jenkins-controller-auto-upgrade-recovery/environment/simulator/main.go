package main

import (
	"encoding/json"
	"encoding/xml"
	"errors"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"regexp"
	"strconv"
	"strings"
)

type controllerDeployment struct {
	Cluster         string `json:"cluster"`
	Namespace       string `json:"namespace"`
	Deployment      string `json:"deployment"`
	Service         string `json:"service"`
	Replicas        int    `json:"replicas"`
	JenkinsVersion  string `json:"jenkins_version"`
	ControllerImage string `json:"controller_image"`
	JavaMajor       int    `json:"java_major"`
	HomeClaim       string `json:"home_claim"`
	HomePath        string `json:"home_path"`
}

type versionInfo struct {
	RequiredJava int `json:"required_java"`
}

type pluginRequirement struct {
	MinCore    string `json:"min_core"`
	MinJava    int    `json:"min_java"`
	MinVersion string `json:"min_version"`
}

type versionContract struct {
	Versions             map[string]versionInfo       `json:"versions"`
	EssentialPlugins     []string                     `json:"essential_plugins"`
	TargetPluginBaseline map[string]pluginRequirement `json:"target_plugin_baseline"`
	RequiredAgentJava    int                          `json:"required_agent_java"`
}

type controllerState struct {
	HomeSchema           string `json:"home_schema"`
	RestoredFromSnapshot string `json:"restored_from_snapshot"`
}

type pluginMeta struct {
	Version string `json:"version"`
	Enabled bool   `json:"enabled"`
}

type upgradePolicy struct {
	AutoUpgradeEnabled     bool   `json:"auto_upgrade_enabled"`
	Channel                string `json:"channel"`
	TargetVersion          string `json:"target_version"`
	PinTargetVersion       bool   `json:"pin_target_version"`
	JavaPreflightRequired  bool   `json:"java_preflight_required"`
	BackupRequired         bool   `json:"backup_required"`
	RequiredBackupSnapshot string `json:"required_backup_snapshot"`
	AbortOnFailedPreflight bool   `json:"abort_on_failed_preflight"`
	LockStrategy           string `json:"lock_strategy"`
}

type service struct {
	Name     string `json:"name"`
	RoutesTo string `json:"routes_to"`
}

type homeClaim struct {
	Name       string `json:"name"`
	AccessMode string `json:"access_mode"`
}

type pod struct {
	Name       string `json:"name"`
	Role       string `json:"role"`
	MountsHome bool   `json:"mounts_home"`
	ReadWrite  bool   `json:"read_write"`
	Elected    bool   `json:"elected"`
}

type agent struct {
	Name              string `json:"name"`
	Online            bool   `json:"online"`
	RemotingJavaMajor int    `json:"remoting_java_major"`
}

type topology struct {
	Service   service   `json:"service"`
	Pods      []pod     `json:"pods"`
	HomeClaim homeClaim `json:"home_claim"`
	Agents    []agent   `json:"agents"`
}

type queueItem struct {
	ID    string `json:"id"`
	Job   string `json:"job"`
	Cause string `json:"cause"`
	State string `json:"state"`
}

type queueState struct {
	Items []queueItem `json:"items"`
}

type jobsState struct {
	Jobs []string `json:"jobs"`
}

type diagnostic struct {
	Phase  string           `json:"phase"`
	Ready  bool             `json:"ready"`
	Checks []map[string]any `json:"checks"`
	Errors []string         `json:"errors"`
}

var splitVersion = regexp.MustCompile(`[.v_-]`)
var digitsOnly = regexp.MustCompile(`^[0-9]+$`)

func appRoot() string {
	if root := os.Getenv("APP_ROOT"); root != "" {
		return root
	}
	return "/app"
}

func appPath(rel string) string {
	return filepath.Join(appRoot(), filepath.FromSlash(rel))
}

func loadJSON(rel string, dst any) error {
	data, err := os.ReadFile(appPath(rel))
	if err != nil {
		return err
	}
	if err := json.Unmarshal(data, dst); err != nil {
		return fmt.Errorf("decode %s: %w", rel, err)
	}
	return nil
}

func writeJSON(rel string, value any) error {
	path := appPath(rel)
	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
		return err
	}
	data, err := json.MarshalIndent(value, "", "  ")
	if err != nil {
		return err
	}
	data = append(data, '\n')
	return os.WriteFile(path, data, 0o644)
}

func versionTuple(value string) [3]int {
	tuple := [3]int{}
	index := 0
	for _, piece := range splitVersion.Split(value, -1) {
		if index == len(tuple) {
			break
		}
		if !digitsOnly.MatchString(piece) {
			continue
		}
		number, err := strconv.Atoi(piece)
		if err != nil {
			continue
		}
		tuple[index] = number
		index++
	}
	return tuple
}

func pluginVersionOK(actual, required string) bool {
	left := versionTuple(actual)
	right := versionTuple(required)
	for i := range left {
		if left[i] > right[i] {
			return true
		}
		if left[i] < right[i] {
			return false
		}
	}
	return true
}

func xmlOK(rel string) bool {
	file, err := os.Open(appPath(rel))
	if err != nil {
		return false
	}
	defer file.Close()
	decoder := xml.NewDecoder(file)
	for {
		_, err := decoder.Token()
		if errors.Is(err, io.EOF) {
			return true
		}
		if err != nil {
			return false
		}
	}
}

func fileContains(rel, text string) bool {
	data, err := os.ReadFile(appPath(rel))
	return err == nil && strings.Contains(string(data), text)
}

func result(phase string, ready bool, checks []map[string]any, errs []string) diagnostic {
	if errs == nil {
		errs = []string{}
	}
	return diagnostic{Phase: phase, Ready: ready, Checks: checks, Errors: errs}
}

func diagnose() (diagnostic, error) {
	checks := []map[string]any{}
	errs := []string{}

	var cluster controllerDeployment
	if err := loadJSON("cluster/controller_deployment.json", &cluster); err != nil {
		return diagnostic{}, err
	}
	var contract versionContract
	if err := loadJSON("config/version_contract.json", &contract); err != nil {
		return diagnostic{}, err
	}

	target := cluster.JenkinsVersion
	version, hasTarget := contract.Versions[target]
	required := version.RequiredJava
	runtimeOK := hasTarget && cluster.JavaMajor >= required && strings.Contains(cluster.ControllerImage, fmt.Sprintf("jdk%d", required))
	checks = append(checks, map[string]any{
		"name":          "runtime",
		"ok":            runtimeOK,
		"target":        target,
		"required_java": required,
		"java_major":    cluster.JavaMajor,
	})
	if !runtimeOK {
		errs = append(errs, "Target Jenkins runtime is not compatible with the configured Java major version")
		return result("RUNTIME_INCOMPATIBLE", false, checks, errs), nil
	}

	var state controllerState
	if err := loadJSON("jenkins_home/controller_state.json", &state); err != nil {
		return diagnostic{}, err
	}
	lockOK := true
	if _, err := os.Stat(appPath("jenkins_home/UPGRADE.lock")); err == nil {
		lockOK = false
	} else if !os.IsNotExist(err) {
		return diagnostic{}, err
	}
	homeOK := xmlOK("jenkins_home/config.xml") &&
		xmlOK("jenkins_home/credentials.xml") &&
		fileContains("jenkins_home/config.xml", "<version>"+target+"</version>") &&
		state.HomeSchema == "recovered-target" &&
		state.RestoredFromSnapshot != ""
	queueXMLOK := xmlOK("jenkins_home/queue.xml")

	jobs := jobsState{Jobs: []string{}}
	if _, err := os.Stat(appPath("jenkins_home/jobs.json")); err == nil {
		if err := loadJSON("jenkins_home/jobs.json", &jobs); err != nil {
			return diagnostic{}, err
		}
	} else if !os.IsNotExist(err) {
		return diagnostic{}, err
	}
	jobSet := map[string]bool{}
	for _, name := range jobs.Jobs {
		jobSet[name] = true
	}
	requiredJobs := []string{"payments-ledger/main", "shared-library/test", "platform-smoke/healthcheck"}
	if state.RestoredFromSnapshot != "" {
		var snapshotJobs jobsState
		if err := loadJSON(filepath.Join("backups", state.RestoredFromSnapshot, "jobs.json"), &snapshotJobs); err == nil {
			requiredJobs = snapshotJobs.Jobs
		}
	}
	jobsOK := len(requiredJobs) > 0
	for _, name := range requiredJobs {
		if !jobSet[name] {
			jobsOK = false
		}
	}
	homeAllOK := homeOK && queueXMLOK && lockOK && jobsOK
	checks = append(checks, map[string]any{
		"name":                "home_integrity",
		"ok":                  homeAllOK,
		"config_xml":          xmlOK("jenkins_home/config.xml"),
		"queue_xml":           queueXMLOK,
		"upgrade_lock_absent": lockOK,
		"jobs_preserved":      jobsOK,
	})
	if !homeAllOK {
		errs = append(errs, "Jenkins home is not safely restored after failed upgrade boot")
		return result("HOME_CORRUPT", false, checks, errs), nil
	}

	plugins := map[string]pluginMeta{}
	if err := loadJSON("jenkins_home/plugins/plugins.json", &plugins); err != nil {
		return diagnostic{}, err
	}
	pluginErrors := []string{}
	for _, name := range contract.EssentialPlugins {
		meta, exists := plugins[name]
		req := contract.TargetPluginBaseline[name]
		switch {
		case !exists || !meta.Enabled:
			pluginErrors = append(pluginErrors, name+":missing-or-disabled")
		case !pluginVersionOK(meta.Version, req.MinVersion):
			pluginErrors = append(pluginErrors, name+":version")
		case req.MinJava > cluster.JavaMajor:
			pluginErrors = append(pluginErrors, name+":java")
		}
	}
	checks = append(checks, map[string]any{
		"name":   "plugins",
		"ok":     len(pluginErrors) == 0,
		"errors": pluginErrors,
	})
	if len(pluginErrors) > 0 {
		errs = append(errs, "Essential plugin baseline is not compatible with the recovered controller")
		return result("PLUGIN_INCOMPATIBLE", false, checks, errs), nil
	}

	var policy upgradePolicy
	if err := loadJSON("cluster/auto_upgrade_policy.json", &policy); err != nil {
		return diagnostic{}, err
	}
	snapshotExists := false
	if policy.RequiredBackupSnapshot != "" {
		info, err := os.Stat(appPath(filepath.Join("backups", policy.RequiredBackupSnapshot)))
		snapshotExists = err == nil && info.IsDir()
	}
	policyOK := !policy.AutoUpgradeEnabled &&
		policy.Channel == "pinned-lts" &&
		policy.TargetVersion == target &&
		policy.PinTargetVersion &&
		policy.JavaPreflightRequired &&
		policy.BackupRequired &&
		snapshotExists &&
		policy.AbortOnFailedPreflight &&
		policy.LockStrategy == "clear-after-verified-restore"
	checks = append(checks, map[string]any{
		"name":            "upgrade_policy",
		"ok":              policyOK,
		"snapshot_exists": snapshotExists,
	})
	if !policyOK {
		errs = append(errs, "Upgrade automation is still unsafe for the recovered controller")
		return result("UNSAFE_AUTOMATION", false, checks, errs), nil
	}

	var topo topology
	if err := loadJSON("cluster/topology.json", &topo); err != nil {
		return diagnostic{}, err
	}
	activeRW := []pod{}
	elected := []pod{}
	for _, p := range topo.Pods {
		if p.Role == "active" && p.MountsHome && p.ReadWrite {
			activeRW = append(activeRW, p)
		}
		if p.Elected {
			elected = append(elected, p)
		}
	}
	serviceOK := len(elected) > 0 && topo.Service.RoutesTo == elected[0].Name
	fencingOK := len(activeRW) == 1 &&
		len(elected) == 1 &&
		activeRW[0].Name == elected[0].Name &&
		topo.HomeClaim.AccessMode == "ReadWriteOnce"
	agentsOK := true
	for _, a := range topo.Agents {
		if a.Online && a.RemotingJavaMajor < contract.RequiredAgentJava {
			agentsOK = false
			break
		}
	}

	queue := queueState{Items: []queueItem{}}
	if _, err := os.Stat(appPath("jenkins_home/queue.json")); err == nil {
		if err := loadJSON("jenkins_home/queue.json", &queue); err != nil {
			return diagnostic{}, err
		}
	} else if !os.IsNotExist(err) {
		return diagnostic{}, err
	}
	ids := map[string]bool{}
	queueOK := true
	for _, item := range queue.Items {
		if strings.TrimSpace(item.ID) == "" || strings.TrimSpace(item.Job) == "" || ids[item.ID] {
			queueOK = false
		}
		ids[item.ID] = true
	}
	clusterOK := serviceOK && fencingOK && agentsOK && queueOK
	checks = append(checks, map[string]any{
		"name":       "cluster_fencing",
		"ok":         clusterOK,
		"service_ok": serviceOK,
		"fencing_ok": fencingOK,
		"agents_ok":  agentsOK,
		"queue_ok":   queueOK,
	})
	if !clusterOK {
		errs = append(errs, "Controller election, route, agent, or queue recovery is unsafe")
		return result("CLUSTER_UNSAFE", false, checks, errs), nil
	}

	return result("READY", true, checks, []string{}), nil
}

func start() (int, error) {
	// A new start attempt must never leave a stale READY status from an earlier run.
	if err := os.Remove(appPath("out/controller_status.json")); err != nil && !os.IsNotExist(err) {
		return 1, err
	}

	diagnosis, err := diagnose()
	if err != nil {
		return 1, err
	}
	if err := writeJSON("out/controller_diagnostics.json", diagnosis); err != nil {
		return 1, err
	}
	if !diagnosis.Ready {
		return 2, nil
	}

	var cluster controllerDeployment
	if err := loadJSON("cluster/controller_deployment.json", &cluster); err != nil {
		return 1, err
	}
	status := map[string]any{
		"status":          "READY",
		"cluster":         cluster.Cluster,
		"deployment":      cluster.Deployment,
		"jenkins_version": cluster.JenkinsVersion,
		"java_major":      cluster.JavaMajor,
		"home_claim":      cluster.HomeClaim,
		"timestamp":       "2026-06-19T00:00:00Z",
	}
	if err := writeJSON("out/controller_status.json", status); err != nil {
		return 1, err
	}
	return 0, nil
}

func printUsage() {
	fmt.Fprintln(os.Stderr, "usage: jenkins_cluster_sim diagnose [--json] | start")
}

func main() {
	if len(os.Args) < 2 {
		printUsage()
		os.Exit(2)
	}

	switch os.Args[1] {
	case "diagnose":
		diagnosis, err := diagnose()
		if err != nil {
			fmt.Fprintln(os.Stderr, err)
			os.Exit(1)
		}
		jsonOutput := false
		for _, arg := range os.Args[2:] {
			if arg == "--json" {
				jsonOutput = true
			} else {
				printUsage()
				os.Exit(2)
			}
		}
		if jsonOutput {
			data, err := json.MarshalIndent(diagnosis, "", "  ")
			if err != nil {
				fmt.Fprintln(os.Stderr, err)
				os.Exit(1)
			}
			fmt.Println(string(data))
		} else {
			fmt.Println(diagnosis.Phase)
		}
		if diagnosis.Ready {
			os.Exit(0)
		}
		os.Exit(2)
	case "start":
		if len(os.Args) != 2 {
			printUsage()
			os.Exit(2)
		}
		code, err := start()
		if err != nil {
			fmt.Fprintln(os.Stderr, err)
			os.Exit(1)
		}
		os.Exit(code)
	default:
		printUsage()
		os.Exit(2)
	}
}
