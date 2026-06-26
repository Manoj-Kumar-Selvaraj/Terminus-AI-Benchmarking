package simclient

import (
	"bytes"
	"encoding/json"
	"fmt"
	"os/exec"
)

const Binary = "/opt/task-tools/lambda-pipeline-runtime"

func Call(command string, input any, output any) error {
	return CallArgs([]string{command}, input, output)
}

func CallArgs(args []string, input any, output any) error {
	var stdin bytes.Buffer
	if input != nil {
		if err := json.NewEncoder(&stdin).Encode(input); err != nil {
			return err
		}
	}
	cmd := exec.Command(Binary, args...)
	cmd.Stdin = &stdin
	var stdout, stderr bytes.Buffer
	cmd.Stdout = &stdout
	cmd.Stderr = &stderr
	if err := cmd.Run(); err != nil {
		return fmt.Errorf("runtime %v: %w: %s", args, err, stderr.String())
	}
	if output == nil {
		return nil
	}
	if err := json.Unmarshal(stdout.Bytes(), output); err != nil {
		return fmt.Errorf("decode runtime %v response %q: %w", args, stdout.String(), err)
	}
	return nil
}

func Now() string {
	var out struct {
		Now string `json:"now"`
	}
	if err := Call("now", nil, &out); err != nil {
		return "1970-01-01T00:00:00Z"
	}
	return out.Now
}
