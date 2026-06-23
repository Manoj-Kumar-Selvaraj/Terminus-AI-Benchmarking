#!/usr/bin/env bash
set -Eeuo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
bash "$SCRIPT_DIR/solve2.sh"
cat > /app/internal/api/handler.go <<'GOFILE'
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

type v1PriceResponse struct {
    SKU         string             `json:"sku"`
    Currency    string             `json:"currency"`
    AmountMinor int64              `json:"amount_minor"`
    Promotion   *catalog.Promotion `json:"promotion"`
}

type v2PriceResponse struct {
    SKU            string             `json:"sku"`
    Currency       string             `json:"currency"`
    AmountMinor    int64              `json:"amount_minor"`
    CatalogVersion int64              `json:"catalog_version"`
    Promotion      *catalog.Promotion `json:"promotion,omitempty"`
}

type notFoundResponse struct {
    Code string `json:"code"`
    SKU  string `json:"sku"`
}

func (h *Handler) ServeHTTP(w http.ResponseWriter, r *http.Request) {
    parts := strings.Split(strings.Trim(r.URL.Path, "/"), "/")
    if len(parts) != 3 || parts[1] != "prices" || (parts[0] != "v1" && parts[0] != "v2") {
        http.NotFound(w, r)
        return
    }

    sku := strings.ToUpper(parts[2])
    currency := r.URL.Query().Get("currency")
    if currency == "" {
        currency = "USD"
    }

    result, err := h.service.GetPrice(r.Context(), sku, currency)
    if errors.Is(err, catalog.ErrNotFound) {
        writeJSON(w, http.StatusNotFound, notFoundResponse{Code: "price_not_found", SKU: sku})
        return
    }
    if err != nil {
        http.Error(w, "catalog unavailable", http.StatusBadGateway)
        return
    }

    price := result.Price
    if parts[0] == "v1" {
        writeJSON(w, http.StatusOK, v1PriceResponse{
            SKU: price.SKU, Currency: price.Currency, AmountMinor: price.AmountMinor, Promotion: price.Promotion,
        })
        return
    }
    writeJSON(w, http.StatusOK, v2PriceResponse{
        SKU: price.SKU, Currency: price.Currency, AmountMinor: price.AmountMinor,
        CatalogVersion: price.Version, Promotion: price.Promotion,
    })
}

func writeJSON(w http.ResponseWriter, status int, value any) {
    w.Header().Set("Content-Type", "application/json")
    w.WriteHeader(status)
    _ = json.NewEncoder(w).Encode(value)
}
GOFILE
/usr/local/go/bin/gofmt -w /app/internal/pricing/service.go /app/internal/api/handler.go
