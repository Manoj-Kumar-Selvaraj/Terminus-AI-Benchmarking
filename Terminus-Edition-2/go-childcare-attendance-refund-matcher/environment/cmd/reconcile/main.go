package main

import (
    "fmt"
    "os"

    "childcare/internal/billing"
)

func main() {
    if err := billing.Run(); err != nil {
        fmt.Fprintln(os.Stderr, err)
        os.Exit(1)
    }
}
