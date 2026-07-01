package main

import (
	"encoding/json"
	"flag"
	"fmt"
	"os"
)

func main() {
	flags := flag.NewFlagSet(os.Args[0], flag.ContinueOnError)
	flags.SetOutput(os.Stderr)
	scenario := flags.String("scenario", "", "mapping, iam, or batch")
	batch := flags.String("batch", "", "batch fixture path")
	cycles := flags.Int("cycles", 1, "delivery cycles")
	resultPath := flags.String("result", "", "optional result file")
	if err := flags.Parse(os.Args[1:]); err != nil {
		os.Exit(2)
	}
	if *scenario != "mapping" && *scenario != "iam" && *scenario != "batch" {
		fmt.Fprintln(os.Stderr, "--scenario must be one of mapping, iam, or batch")
		os.Exit(2)
	}

	var result map[string]any
	var err error
	switch *scenario {
	case "mapping":
		result, err = mappingProbe()
	case "iam":
		result, err = iamProbe()
	case "batch":
		if *batch == "" {
			fmt.Fprintln(os.Stderr, "--batch is required for batch scenario")
			os.Exit(2)
		}
		result, err = simulateBatch(*batch, *cycles)
	}
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
	if *resultPath != "" {
		if err := saveJSON(*resultPath, result); err != nil {
			fmt.Fprintln(os.Stderr, err)
			os.Exit(1)
		}
	}
	output, err := json.MarshalIndent(result, "", "  ")
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
	fmt.Println(string(output))
}
