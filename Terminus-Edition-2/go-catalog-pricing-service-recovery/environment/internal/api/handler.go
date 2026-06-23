package api

import (
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"strings"

	"catalog-pricing-service/internal/catalog"
	"catalog-pricing-service/internal/pricing"
)

type PriceService interface {
	GetPrice(ctx context.Context, sku, currency string) (pricing.Result, error)
}

type Handler struct {
	service PriceService
}

func NewHandler(service PriceService) *Handler {
	return &Handler{service: service}
}

func (h *Handler) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	parts := strings.Split(strings.Trim(r.URL.Path, "/"), "/")
	if len(parts) != 3 || parts[1] != "prices" {
		http.NotFound(w, r)
		return
	}

	currency := r.URL.Query().Get("currency")
	if currency == "" {
		currency = "USD"
	}

	result, err := h.service.GetPrice(r.Context(), parts[2], currency)
	if errors.Is(err, catalog.ErrNotFound) {
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusNotFound)
		_ = json.NewEncoder(w).Encode(map[string]string{"error": err.Error()})
		return
	}
	if err != nil {
		http.Error(w, "catalog unavailable", http.StatusBadGateway)
		return
	}

	w.Header().Set("Content-Type", "application/json")
	_ = json.NewEncoder(w).Encode(result)
}
