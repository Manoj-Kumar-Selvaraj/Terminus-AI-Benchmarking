package main

import (
	"fmt"
	"os"
	"os/exec"
)

func run(command *exec.Cmd) int {
	command.Stdout = os.Stdout
	command.Stderr = os.Stderr
	command.Stdin = os.Stdin
	if err := command.Run(); err != nil {
		if exitError, ok := err.(*exec.ExitError); ok {
			return exitError.ExitCode()
		}
		fmt.Fprintln(os.Stderr, err)
		return 1
	}
	return 0
}

func main() {
	compile := exec.Command("go", "build", "-o", "/tmp/ec2sim-runtime", "./cmd/ec2sim")
	compile.Dir = "/app"
	if code := run(compile); code != 0 {
		os.Exit(code)
	}
	execute := exec.Command("/tmp/ec2sim-runtime", os.Args[1:]...)
	if code := run(execute); code != 0 {
		os.Exit(code)
	}
}
