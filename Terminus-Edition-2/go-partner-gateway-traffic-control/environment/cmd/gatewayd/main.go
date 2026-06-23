package main

import (
	"encoding/json"
	"log"
	"net/http"
	"os"
	"time"

	"partner-gateway-traffic-control/internal/gateway"
	"partner-gateway-traffic-control/internal/limiter"
)

type policy struct {
	RatePerSecond float64 `json:"rate_per_second"`
	Burst         int     `json:"burst"`
}

func main() {
	configPath := os.Getenv("TRAFFIC_POLICY_PATH")
	if configPath == "" {
		configPath = "/app/config/limits.json"
	}

	raw, err := os.ReadFile(configPath)
	if err != nil {
		log.Fatal(err)
	}
	var configured policy
	if err := json.Unmarshal(raw, &configured); err != nil {
		log.Fatal(err)
	}

	trafficLimiter := limiter.New(configured.RatePerSecond, configured.Burst, time.Now)
	accepted := http.HandlerFunc(func(response http.ResponseWriter, request *http.Request) {
		response.Header().Set("Content-Type", "application/json")
		_, _ = response.Write([]byte(`{"status":"accepted"}`))
	})

	handler := gateway.NewMiddleware(trafficLimiter, accepted)
	log.Fatal(http.ListenAndServe(":8080", handler))
}
