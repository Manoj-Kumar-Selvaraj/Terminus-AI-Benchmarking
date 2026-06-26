package main

import (
	"encoding/json"
	"flag"
	"fmt"
	"os"
	"path/filepath"
	"strings"

	"ec2sim/infra/modules/ec2"
)

func load(path string) (ec2.Value, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	result := ec2.Value{}
	if err := json.Unmarshal(data, &result); err != nil {
		return nil, err
	}
	return result, nil
}

func atomicWrite(path string, value any) error {
	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
		return err
	}
	data, err := json.MarshalIndent(value, "", "  ")
	if err != nil {
		return err
	}
	data = append(data, '\n')
	temporary, err := os.CreateTemp(filepath.Dir(path), filepath.Base(path)+".")
	if err != nil {
		return err
	}
	temporaryName := temporary.Name()
	defer os.Remove(temporaryName)
	if _, err := temporary.Write(data); err == nil {
		err = temporary.Sync()
	}
	if closeErr := temporary.Close(); err == nil {
		err = closeErr
	}
	if err != nil {
		return err
	}
	return os.Rename(temporaryName, path)
}

func repairJournal(path string) ([]ec2.Value, ec2.Value, error) {
	data, err := os.ReadFile(path)
	if os.IsNotExist(err) {
		return []ec2.Value{}, ec2.Value{"truncated_tail": false, "preserved_records": 0}, nil
	}
	if err != nil {
		return nil, nil, err
	}
	lines := strings.Split(strings.TrimSuffix(string(data), "\n"), "\n")
	records := []ec2.Value{}
	truncated := false
	for index, line := range lines {
		if strings.TrimSpace(line) == "" {
			continue
		}
		value := ec2.Value{}
		if err := json.Unmarshal([]byte(line), &value); err != nil {
			if index != len(lines)-1 {
				return nil, nil, fmt.Errorf("invalid interior journal record at line %d", index+1)
			}
			truncated = true
			continue
		}
		records = append(records, value)
	}
	if truncated {
		contents := []byte{}
		for _, record := range records {
			line, _ := json.Marshal(record)
			contents = append(contents, line...)
			contents = append(contents, '\n')
		}
		if err := os.WriteFile(path, contents, 0o644); err != nil {
			return nil, nil, err
		}
	}
	return records, ec2.Value{"truncated_tail": truncated, "preserved_records": len(records)}, nil
}

func appendJournal(path string, record ec2.Value) error {
	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
		return err
	}
	file, err := os.OpenFile(path, os.O_APPEND|os.O_CREATE|os.O_WRONLY, 0o644)
	if err != nil {
		return err
	}
	defer file.Close()
	data, _ := json.Marshal(record)
	if _, err := file.Write(append(data, '\n')); err != nil {
		return err
	}
	return file.Sync()
}

func main() {
	if len(os.Args) < 2 {
		fmt.Fprintln(os.Stderr, "usage: ec2sim <plan|apply|validate> [flags]")
		os.Exit(2)
	}
	command := os.Args[1]
	if command != "plan" && command != "apply" && command != "validate" {
		fmt.Fprintln(os.Stderr, "unknown command")
		os.Exit(2)
	}
	flags := flag.NewFlagSet(command, flag.ContinueOnError)
	flags.SetOutput(os.Stderr)
	configPath := flags.String("config", "/app/infra/envs/prod/ec2_config.json", "configuration file")
	priorPath := flags.String("prior-state", "", "prior state")
	outPath := flags.String("out", "", "output path")
	statePath := flags.String("state", "/app/state/ec2_state.json", "state path")
	journalPath := flags.String("journal", "", "journal path")
	if err := flags.Parse(os.Args[2:]); err != nil {
		os.Exit(2)
	}
	if *journalPath == "" {
		*journalPath = *statePath + ".journal.jsonl"
	}
	writeError := func(err error) {
		result := ec2.Value{"valid": false, "error": err.Error()}
		if *outPath != "" {
			_ = atomicWrite(*outPath, result)
		} else {
			data, _ := json.MarshalIndent(result, "", "  ")
			fmt.Fprintln(os.Stderr, string(data))
		}
		os.Exit(2)
	}
	config, err := load(*configPath)
	if err != nil {
		writeError(err)
	}
	prior := ec2.Value{}
	if *priorPath != "" {
		prior, err = load(*priorPath)
		if err != nil {
			writeError(err)
		}
	} else if command == "apply" {
		if _, statErr := os.Stat(*statePath); statErr == nil {
			prior, err = load(*statePath)
			if err != nil {
				writeError(err)
			}
		}
	}
	_, repair, err := repairJournal(*journalPath)
	if err != nil {
		writeError(err)
	}
	var result ec2.Value
	if command == "validate" {
		if err := ec2.ValidateConfig(config); err != nil {
			writeError(err)
		}
		result = ec2.Value{"valid": true, "schema_version": config["schema_version"], "environment": config["environment"], "journal_repair": repair}
	} else {
		result, err = ec2.Render(config, prior)
		if err != nil {
			writeError(err)
		}
		result["journal_repair"] = repair
		if command == "apply" {
			if err := atomicWrite(*statePath, result); err != nil {
				writeError(err)
			}
			outputs := object(result["outputs"])
			release := object(result["release_identity"])
			refresh := object(object(result["autoscaling_group"])["instance_refresh"])
			if err := appendJournal(*journalPath, ec2.Value{"operation_id": outputs["rollout_operation_id"], "release_manifest_sha256": release["manifest_sha256"], "refresh_status": refresh["status"], "state_digest": result["state_digest"]}); err != nil {
				writeError(err)
			}
		}
	}
	if *outPath != "" {
		if err := atomicWrite(*outPath, result); err != nil {
			writeError(err)
		}
	} else {
		data, _ := json.MarshalIndent(result, "", "  ")
		fmt.Println(string(data))
	}
	if command == "apply" && result["control_plane_response_lost"] == true {
		os.Exit(3)
	}
}

func object(value any) ec2.Value {
	if result, ok := value.(ec2.Value); ok {
		return result
	}
	if result, ok := value.(map[string]any); ok {
		return result
	}
	return ec2.Value{}
}
