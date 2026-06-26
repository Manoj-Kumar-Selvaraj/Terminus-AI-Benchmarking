package main

import (
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"os"
	"path/filepath"

	"jenkins-lambda-cutover/internal/cutover"
	"jenkins-lambda-cutover/internal/engine"
	"jenkins-lambda-cutover/internal/iac"
	"jenkins-lambda-cutover/internal/model"
	"jenkins-lambda-cutover/internal/recovery"
	"jenkins-lambda-cutover/internal/simclient"
	"jenkins-lambda-cutover/internal/store"
)

func main() {
	if err := run(); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}
func run() error {
	if len(os.Args) < 2 {
		return errors.New("command required: deploy|run|resume|cutover|rollback|jenkins-shadow|reconcile|inspect")
	}
	switch os.Args[1] {
	case "deploy":
		fs := flag.NewFlagSet("deploy", flag.ContinueOnError)
		infra := fs.String("infra", "/app/infra", "infra directory")
		if err := fs.Parse(os.Args[2:]); err != nil {
			return err
		}
		d, err := iac.Load(*infra)
		if err != nil {
			return err
		}
		if err := engine.Deploy(*infra, d); err != nil {
			return err
		}
		return printJSON(d)
	case "run":
		fs := flag.NewFlagSet("run", flag.ContinueOnError)
		path := fs.String("request", "", "request file")
		if err := fs.Parse(os.Args[2:]); err != nil {
			return err
		}
		if *path == "" {
			return errors.New("--request required")
		}
		r, err := readRequest(*path)
		if err != nil {
			return err
		}
		r, err = recovery.Normalize(r)
		if err != nil {
			return err
		}
		if err := persistRequest(r); err != nil {
			return err
		}
		cp, err := engine.Run(r)
		_ = printJSON(cp)
		return err
	case "resume":
		fs := flag.NewFlagSet("resume", flag.ContinueOnError)
		id := fs.String("execution", "", "execution id")
		if err := fs.Parse(os.Args[2:]); err != nil {
			return err
		}
		cp, err := store.LoadCheckpoint(*id)
		if err != nil {
			return err
		}
		r, err := recovery.LoadRequestForCheckpoint(cp)
		if err != nil {
			return err
		}
		r, err = recovery.Normalize(r)
		if err != nil {
			return err
		}
		cp, err = engine.Resume(r, cp)
		_ = printJSON(cp)
		return err
	case "cutover":
		fs := flag.NewFlagSet("cutover", flag.ContinueOnError)
		g := fs.Int("generation", 0, "generation")
		writer := fs.String("writer", "lambda", "writer")
		if err := fs.Parse(os.Args[2:]); err != nil {
			return err
		}
		c, err := cutover.Shift(*g, *writer)
		if err != nil {
			return err
		}
		return printJSON(c)
	case "rollback":
		fs := flag.NewFlagSet("rollback", flag.ContinueOnError)
		g := fs.Int("generation", 0, "generation")
		if err := fs.Parse(os.Args[2:]); err != nil {
			return err
		}
		c, err := cutover.Shift(*g, "lambda")
		if err != nil {
			return err
		}
		return printJSON(c)
	case "jenkins-shadow":
		fs := flag.NewFlagSet("jenkins-shadow", flag.ContinueOnError)
		path := fs.String("request", "", "request file")
		if err := fs.Parse(os.Args[2:]); err != nil {
			return err
		}
		r, err := readRequest(*path)
		if err != nil {
			return err
		}
		c, err := cutover.Load()
		if err != nil {
			return err
		}
		var out map[string]any
		err = simclient.Call("jenkins-run", map[string]any{"batch_id": r.BatchID, "write": c.Writer == "jenkins"}, &out)
		if err != nil {
			return err
		}
		return printJSON(out)
	case "reconcile":
		repairedJournal, err := recovery.RepairJournal()
		if err != nil {
			return err
		}
		repairedDrift, err := recovery.RepairDrift()
		if err != nil {
			return err
		}
		ids, err := recovery.PendingExecutions()
		if err != nil {
			return err
		}
		resumed := []string{}
		for _, id := range ids {
			cp, e := store.LoadCheckpoint(id)
			if e != nil {
				return e
			}
			r, e := recovery.LoadRequestForCheckpoint(cp)
			if e != nil {
				return e
			}
			r, e = recovery.Normalize(r)
			if e != nil {
				return e
			}
			if _, e = engine.Resume(r, cp); e == nil {
				resumed = append(resumed, id)
			}
		}
		return printJSON(map[string]any{"journal_repaired": repairedJournal, "drift_repaired": repairedDrift, "resumed": resumed})
	case "inspect":
		fs := flag.NewFlagSet("inspect", flag.ContinueOnError)
		what := fs.String("what", "cutover", "cutover|execution|runtime")
		id := fs.String("execution", "", "execution id")
		if err := fs.Parse(os.Args[2:]); err != nil {
			return err
		}
		switch *what {
		case "cutover":
			c, err := cutover.Load()
			if err != nil {
				return err
			}
			return printJSON(c)
		case "execution":
			cp, err := store.LoadCheckpoint(*id)
			if err != nil {
				return err
			}
			return printJSON(cp)
		case "runtime":
			var out map[string]any
			if err := simclient.CallArgs([]string{"inspect", "state"}, nil, &out); err != nil {
				return err
			}
			return printJSON(out)
		default:
			return errors.New("unknown inspect target")
		}
	default:
		return fmt.Errorf("unknown command %q", os.Args[1])
	}
}
func readRequest(path string) (model.Request, error) {
	var r model.Request
	b, err := os.ReadFile(path)
	if err != nil {
		return r, err
	}
	err = json.Unmarshal(b, &r)
	return r, err
}
func persistRequest(r model.Request) error {
	path := filepath.Join("/app/state/requests", r.ExecutionID+".json")
	return store.AtomicWriteJSON(path, r)
}
func printJSON(v any) error { return json.NewEncoder(os.Stdout).Encode(v) }
