package main

import (
	"cardrollout/internal/cli"
	"cardrollout/internal/controller"
	"cardrollout/internal/store"
	"context"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"os"
	"strings"
	"time"
)

func main() {
	if len(os.Args) < 2 {
		usage()
		os.Exit(2)
	}
	var err error
	switch os.Args[1] {
	case "enqueue":
		err = runEnqueue(os.Args[2:])
	case "dispatch":
		err = runDispatch(os.Args[2:])
	case "status":
		err = runStatus(os.Args[2:])
	case "compact":
		err = runCompact(os.Args[2:])
	default:
		usage()
		os.Exit(2)
	}
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		if errors.Is(err, store.ErrInjectedCompactionStop) {
			os.Exit(87)
		}
		os.Exit(1)
	}
}

func usage() {
	fmt.Fprintln(os.Stderr, "usage: rolloutctl <enqueue|dispatch|status|compact> [options]")
}

func runEnqueue(args []string) error {
	fs := flag.NewFlagSet("enqueue", flag.ContinueOnError)
	stateDir := fs.String("state", "", "controller state directory")
	rolloutID := fs.String("rollout", "", "rollout id")
	generation := fs.Int64("generation", 0, "policy generation")
	policyFile := fs.String("policy", "", "policy JSON file")
	regionsCSV := fs.String("regions", "", "comma-separated regions")
	if err := fs.Parse(args); err != nil {
		return err
	}
	if *stateDir == "" || *policyFile == "" {
		return errors.New("--state and --policy are required")
	}
	policy, err := os.ReadFile(*policyFile)
	if err != nil {
		return err
	}
	return controller.Enqueue(store.New(*stateDir), *rolloutID, *generation, string(policy), strings.Split(*regionsCSV, ","))
}

func runDispatch(args []string) error {
	fs := flag.NewFlagSet("dispatch", flag.ContinueOnError)
	stateDir := fs.String("state", "", "controller state directory")
	gatewayFile := fs.String("gateways", "", "region to endpoint JSON file")
	workers := fs.Int("workers", 1, "worker count")
	workerID := fs.String("worker-id", "worker", "worker identity")
	nowUnix := fs.Int64("now-unix", time.Now().Unix(), "logical current Unix time")
	failpoint := fs.String("failpoint", "", "test-only process stop point")
	if err := fs.Parse(args); err != nil {
		return err
	}
	if *stateDir == "" || *gatewayFile == "" {
		return errors.New("--state and --gateways are required")
	}
	gateways, err := cli.ReadGatewayMap(*gatewayFile)
	if err != nil {
		return err
	}
	return controller.Dispatch(context.Background(), store.New(*stateDir), controller.DispatchOptions{
		WorkerID:  *workerID,
		Workers:   *workers,
		NowUnix:   *nowUnix,
		Failpoint: *failpoint,
		Gateways:  gateways,
	})
}

func runStatus(args []string) error {
	fs := flag.NewFlagSet("status", flag.ContinueOnError)
	stateDir := fs.String("state", "", "controller state directory")
	if err := fs.Parse(args); err != nil {
		return err
	}
	if *stateDir == "" {
		return errors.New("--state is required")
	}
	doc, err := controller.Status(store.New(*stateDir))
	if err != nil {
		return err
	}
	enc := json.NewEncoder(os.Stdout)
	enc.SetIndent("", "  ")
	return enc.Encode(doc)
}

func runCompact(args []string) error {
	fs := flag.NewFlagSet("compact", flag.ContinueOnError)
	stateDir := fs.String("state", "", "controller state directory")
	failpoint := fs.String("failpoint", "", "test-only process stop point")
	if err := fs.Parse(args); err != nil {
		return err
	}
	if *stateDir == "" {
		return errors.New("--state is required")
	}
	return store.New(*stateDir).Compact(*failpoint)
}
