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
	abendAfterLimMaster := flag.Bool("abend-after-lim-master", false, "abort mid-LIM after master commit before risk commit")
	closeDate := flag.String("close", "", "end-of-day close ceremony for the given business date")
	flag.Parse()

	if *closeDate != "" {
		if *dbPath == "" || *out == "" {
			os.Stderr.WriteString("usage: finbulk --close DATE --db PATH --out PATH\n")
			os.Exit(99)
		}
	} else if *input == "" || *dbPath == "" || *out == "" {
		os.Stderr.WriteString("usage: finbulk --input PATH --db PATH --out PATH [--batch ID] [--abend-after N] [--abend-after-lim-master] [--control PATH]\n")
		os.Exit(99)
	}

	args := finbulk.Args{
		Batch: *batch, Input: *input, DB: *dbPath, Out: *out,
		Control: *control, AbendAfter: *abendAfter,
		AbendAfterLimMaster: *abendAfterLimMaster,
		CloseDate:           *closeDate,
	}
	os.Exit(finbulk.Run(args, finbulk.Profile))
}
