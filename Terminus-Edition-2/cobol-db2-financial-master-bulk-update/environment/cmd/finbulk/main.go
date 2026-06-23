package main

import (
	"flag"
	"os"

	"finbulk/internal/finbulk"
)

func main() {
	batch := flag.String("batch", "", "batch id override")
	input := flag.String("input", "", "fixed-width input file")
	dbPath := flag.String("db", "", "simulator database json")
	out := flag.String("out", "", "output directory")
	control := flag.String("control", "", "optional control manifest json")
	abendAfter := flag.Int("abend-after", 0, "simulate abend after N applied details")
	flag.Parse()

	if *input == "" || *dbPath == "" || *out == "" {
		os.Stderr.WriteString("usage: finbulk --input PATH --db PATH --out PATH [--batch ID] [--abend-after N] [--control PATH]\n")
		os.Exit(99)
	}

	args := finbulk.Args{
		Batch: *batch, Input: *input, DB: *dbPath, Out: *out,
		Control: *control, AbendAfter: *abendAfter,
	}
	os.Exit(finbulk.Run(args, finbulk.Profile))
}
