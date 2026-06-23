package main

import (
    "fmt"
    "os"

    "go-escape-room-booking-refund-matcher/internal/reconcile"
)

func main() {
    if err := reconcile.Run(); err != nil {
        fmt.Fprintln(os.Stderr, err)
        os.Exit(1)
    }
}
