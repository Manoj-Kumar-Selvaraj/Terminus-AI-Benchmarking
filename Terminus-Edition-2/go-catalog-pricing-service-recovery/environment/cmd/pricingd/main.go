package main

import (
	"fmt"
	"net/http"
	"os"
	"time"

	"catalog-pricing-service/internal/api"
	"catalog-pricing-service/internal/cache"
	"catalog-pricing-service/internal/catalog"
	"catalog-pricing-service/internal/pricing"
)

func main() {
	source := catalog.NewMemorySource([]catalog.Price{
		{SKU: "CAMERA-4K", Currency: "USD", AmountMinor: 129900, Version: 41},
		{SKU: "CAMERA-4K", Currency: "INR", AmountMinor: 10899000, Version: 41},
	})
	store := cache.NewStore(30*time.Second, nil)
	service := pricing.NewService(store, source)
	handler := api.NewHandler(service)

	addr := ":8080"
	if value := os.Getenv("PRICING_ADDR"); value != "" {
		addr = value
	}
	fmt.Printf("pricingd listening on %s\n", addr)
	if err := http.ListenAndServe(addr, handler); err != nil {
		os.Exit(1)
	}
}
