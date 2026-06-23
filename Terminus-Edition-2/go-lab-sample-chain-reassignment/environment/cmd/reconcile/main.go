package main

import (
	"log"

	"golabsamplechainreassignment/internal/reconcile"
)

func main() {
	if err := reconcile.Run("/app"); err != nil {
		log.Fatal(err)
	}
}
