package main

import (
	"cardrollout/internal/gateway"
	"errors"
	"flag"
	"fmt"
	"net/http"
	"os"
)

func main() {
	fs := flag.NewFlagSet("gatewayd", flag.ExitOnError)
	region := fs.String("region", "", "gateway region")
	statePath := fs.String("state", "", "persistent gateway state file")
	listen := fs.String("listen", "127.0.0.1:0", "listen address")
	holdGeneration := fs.Int64("hold-generation", 0, "test-only held generation")
	startedFile := fs.String("started-file", "", "test-only request marker")
	releaseFile := fs.String("release-file", "", "test-only release marker")
	_ = fs.Parse(os.Args[1:])
	if *region == "" || *statePath == "" {
		fmt.Fprintln(os.Stderr, "--region and --state are required")
		os.Exit(2)
	}
	state, err := gateway.NewStateFile(*region, *statePath)
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
	handler := gateway.Handler(state, gateway.ServerOptions{
		Region: *region, StatePath: *statePath, HoldGeneration: *holdGeneration,
		StartedFile: *startedFile, ReleaseFile: *releaseFile,
	})
	server := &http.Server{Addr: *listen, Handler: handler, ReadHeaderTimeout: 5_000_000_000}
	fmt.Fprintf(os.Stdout, "gatewayd region=%s listen=%s\n", *region, *listen)
	if err := server.ListenAndServe(); err != nil && !errors.Is(err, http.ErrServerClosed) {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}
