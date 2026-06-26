package main

import (
	"encoding/json"
	"flag"
	"fmt"
	"os"
	"path/filepath"

	"vpc-egress-sim/infra/modules/vpc"
)

func load(path string) (map[string]interface{}, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	var out map[string]interface{}
	if err := json.Unmarshal(data, &out); err != nil {
		return nil, err
	}
	return out, nil
}

func write(path string, obj interface{}) error {
	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
		return err
	}
	data, err := json.MarshalIndent(obj, "", "  ")
	if err != nil {
		return err
	}
	data = append(data, '\n')
	return os.WriteFile(path, data, 0o644)
}

func fail(outPath string, msg string) int {
	res := map[string]interface{}{"valid": false, "error": msg}
	if outPath != "" {
		_ = write(outPath, res)
	} else {
		enc, _ := json.MarshalIndent(res, "", "  ")
		fmt.Fprintln(os.Stderr, string(enc))
	}
	return 2
}

func main() {
	if len(os.Args) < 2 {
		fmt.Fprintln(os.Stderr, "subcommand required: plan, apply, or validate")
		os.Exit(1)
	}
	cmd := os.Args[1]
	fs := flag.NewFlagSet(cmd, flag.ExitOnError)
	config := fs.String("config", "/app/infra/envs/prod/vpc_config.json", "config file")
	priorState := fs.String("prior-state", "", "prior state file")
	out := fs.String("out", "", "output file")
	state := fs.String("state", "/app/state/vpc_state.json", "state file")
	_ = fs.Parse(os.Args[2:])

	cfg, err := load(*config)
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
	var prior map[string]interface{}
	if *priorState != "" {
		prior, err = load(*priorState)
		if err != nil {
			fmt.Fprintln(os.Stderr, err)
			os.Exit(1)
		}
	}

	switch cmd {
	case "validate":
		if err := vpc.ValidateConfig(cfg); err != nil {
			os.Exit(fail(*out, err.Error()))
		}
		res := map[string]interface{}{"valid": true, "environment": cfg["environment"]}
		if *out != "" {
			if err := write(*out, res); err != nil {
				fmt.Fprintln(os.Stderr, err)
				os.Exit(1)
			}
		} else {
			enc, _ := json.MarshalIndent(res, "", "  ")
			fmt.Println(string(enc))
		}
	case "plan", "apply":
		res, err := vpc.Render(cfg, prior)
		if err != nil {
			os.Exit(fail(*out, err.Error()))
		}
		if cmd == "apply" {
			if err := write(*state, res); err != nil {
				fmt.Fprintln(os.Stderr, err)
				os.Exit(1)
			}
		}
		if *out != "" {
			if err := write(*out, res); err != nil {
				fmt.Fprintln(os.Stderr, err)
				os.Exit(1)
			}
		} else {
			enc, _ := json.MarshalIndent(res, "", "  ")
			fmt.Println(string(enc))
		}
	default:
		fmt.Fprintf(os.Stderr, "unknown subcommand: %s\n", cmd)
		os.Exit(1)
	}
}
