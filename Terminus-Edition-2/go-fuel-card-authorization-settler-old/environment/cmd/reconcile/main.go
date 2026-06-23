package main

import (
	"fmt"
	"os"

	"gofuelcardauthorizationsettler/internal/reconcile"
)

func main() {
	if err := reconcile.Run(); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}
