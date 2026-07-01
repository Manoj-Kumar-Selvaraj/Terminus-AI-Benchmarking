package main

import (
	"flag"
	"fmt"
	"os"
)

func main() {
	if len(os.Args) < 2 {
		fmt.Fprintln(os.Stderr, "usage: jenkins-recover inspect|plan|apply|resume|verify")
		os.Exit(2)
	}
	fs := flag.NewFlagSet(os.Args[1], flag.ContinueOnError)
	_ = fs.String("owner", "", "")
	_ = fs.String("fault", "", "")
	_ = fs.Bool("json", false, "")
	_ = fs.Int("hold-ms", 0, "")
	_ = fs.Parse(os.Args[2:])
	fmt.Fprintln(os.Stderr, "recovery controller is not implemented")
	os.Exit(1)
}
