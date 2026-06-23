package main

import (
	"context"
	"flag"
	"fmt"
	"log"
	"net/http"
	"time"

	"edge-gateway-tls-recovery/internal/config"
	"edge-gateway-tls-recovery/internal/tlsmaterial"
	"edge-gateway-tls-recovery/internal/upstream"
)

func main() {
	configPath := flag.String("config", "/app/config/gateway.json", "gateway configuration")
	flag.Parse()

	cfg, err := config.Load(*configPath)
	if err != nil {
		log.Fatal(err)
	}
	manager, err := tlsmaterial.NewManager(tlsmaterial.Config{
		RootCAFile:     cfg.RootCAFile,
		ServerName:     cfg.ServerName,
		ClientCertFile: cfg.ClientCertFile,
		ClientKeyFile:  cfg.ClientKeyFile,
	})
	if err != nil {
		log.Fatal(err)
	}
	client := upstream.NewClient(manager)

	mux := http.NewServeMux()
	mux.HandleFunc("/healthz", func(w http.ResponseWriter, _ *http.Request) {
		_, _ = w.Write([]byte("ok"))
	})
	mux.HandleFunc("/fetch", func(w http.ResponseWriter, r *http.Request) {
		ctx, cancel := context.WithTimeout(r.Context(), 3*time.Second)
		defer cancel()
		body, err := client.Get(ctx, cfg.UpstreamURL)
		if err != nil {
			http.Error(w, err.Error(), http.StatusBadGateway)
			return
		}
		_, _ = fmt.Fprint(w, string(body))
	})
	log.Fatal(http.ListenAndServe(cfg.ListenAddress, mux))
}
