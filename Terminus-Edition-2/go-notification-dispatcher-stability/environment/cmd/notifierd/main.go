package main

import (
	"context"
	"fmt"
	"net/http"
	"os"
	"strconv"
	"time"

	"notification-dispatcher/internal/delivery"
	"notification-dispatcher/internal/dispatch"
	"notification-dispatcher/internal/idempotency"
)

func main() {
	workers := envInt("NOTIFIER_WORKERS", 4)
	port := envInt("NOTIFIER_PORT", 8080)

	ledger := idempotency.NewLedger()
	httpClient := &http.Client{Timeout: 5 * time.Second}
	deliverer := delivery.NewClient(httpClient, ledger)

	d := dispatch.NewDispatcher(workers, func(ctx context.Context, job dispatch.Job) error {
		return deliverer.DeliverWithRetry(ctx, job)
	})

	mux := http.NewServeMux()
	mux.HandleFunc("/healthz", func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte("ok"))
	})
	mux.HandleFunc("/enqueue", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
			return
		}
		job := dispatch.Job{
			OperationKey: r.URL.Query().Get("key"),
			ClientID:     r.URL.Query().Get("client"),
			TargetURL:    r.URL.Query().Get("target"),
			EventType:    r.URL.Query().Get("event"),
			Payload: map[string]string{
				"account_id": r.URL.Query().Get("account"),
				"amount":     r.URL.Query().Get("amount"),
				"trace_id":   r.URL.Query().Get("trace"),
			},
		}
		if err := d.Enqueue(job); err != nil {
			http.Error(w, err.Error(), http.StatusBadRequest)
			return
		}
		w.WriteHeader(http.StatusAccepted)
	})

	addr := fmt.Sprintf(":%d", port)
	fmt.Printf("notifierd listening on %s with %d workers\n", addr, workers)
	if err := http.ListenAndServe(addr, mux); err != nil {
		os.Exit(1)
	}
}

func envInt(name string, fallback int) int {
	raw := os.Getenv(name)
	if raw == "" {
		return fallback
	}
	value, err := strconv.Atoi(raw)
	if err != nil {
		return fallback
	}
	return value
}
