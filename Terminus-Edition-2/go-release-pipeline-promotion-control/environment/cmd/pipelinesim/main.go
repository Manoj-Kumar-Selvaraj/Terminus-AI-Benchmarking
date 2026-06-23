package main

import (
	"flag"
	"fmt"
	"os"

	"releasepipeline/internal/pipeline"
)

func main() {
	if len(os.Args) < 2 {
		usage()
		os.Exit(2)
	}

	switch os.Args[1] {
	case "run":
		fs := flag.NewFlagSet("run", flag.ExitOnError)
		scenarioPath := fs.String("scenario", "/app/scenarios/release_candidate.json", "path to release scenario JSON")
		outDir := fs.String("out", "/app/out/pipeline", "output directory for pipeline artifacts")
		if err := fs.Parse(os.Args[2:]); err != nil {
			fmt.Fprintln(os.Stderr, err)
			os.Exit(2)
		}
		scenario, err := pipeline.LoadScenario(*scenarioPath)
		if err != nil {
			fmt.Fprintln(os.Stderr, err)
			os.Exit(1)
		}
		if err := pipeline.RunPipeline(scenario, *outDir); err != nil {
			fmt.Fprintln(os.Stderr, err)
			os.Exit(1)
		}
	case "rollback":
		fs := flag.NewFlagSet("rollback", flag.ExitOnError)
		historyPath := fs.String("history", "/app/out/pipeline/release/release_history.json", "path to release history JSON")
		outDir := fs.String("out", "/app/out/rollback", "output directory for rollback manifest")
		env := fs.String("env", "prod", "deployment environment to roll back")
		targetBuild := fs.String("target-build", "", "optional build number to redeploy from release history")
		if err := fs.Parse(os.Args[2:]); err != nil {
			fmt.Fprintln(os.Stderr, err)
			os.Exit(2)
		}
		if err := pipeline.ExecuteRollback(*historyPath, *outDir, *env, *targetBuild); err != nil {
			fmt.Fprintln(os.Stderr, err)
			os.Exit(1)
		}
	default:
		usage()
		os.Exit(2)
	}
}

func usage() {
	fmt.Fprintln(os.Stderr, "usage: pipelinesim run --scenario PATH --out DIR | pipelinesim rollback --history PATH --env ENV --out DIR [--target-build BUILD]")
}
