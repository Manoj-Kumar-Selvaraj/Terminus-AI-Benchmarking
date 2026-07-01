package main

import (
	"encoding/json"
	"flag"
	"fmt"
	"os"
)

func main() {
	if len(os.Args) < 2 {
		fmt.Fprintln(os.Stderr, "subcommand required")
		os.Exit(1)
	}
	cmd := os.Args[1]
	fs := flag.NewFlagSet(cmd, flag.ExitOnError)
	_ = fs.String("root", "/app", "")
	jsonOut := fs.Bool("json", false, "")
	_ = fs.String("owner", "", "")
	_ = fs.String("fail-after", "", "")
	_ = fs.Parse(os.Args[2:])
	_ = jsonOut
	out := map[string]any{"valid": false, "phase": "ROUTE_DRIFT_UNRECOVERED", "error": "vpc recovery controller has not implemented transactional route recovery"}
	b, _ := json.MarshalIndent(out, "", "  ")
	fmt.Println(string(b))
	if cmd != "inspect" && cmd != "plan" {
		os.Exit(2)
	}
}
