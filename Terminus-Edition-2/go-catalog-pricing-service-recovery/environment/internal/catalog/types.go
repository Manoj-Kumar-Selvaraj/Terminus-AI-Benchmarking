package catalog

import (
	"context"
	"errors"
)

var ErrNotFound = errors.New("price not found")

type Promotion struct {
	Code  string `json:"code"`
	Label string `json:"label"`
}

type Price struct {
	SKU         string     `json:"sku"`
	Currency    string     `json:"currency"`
	AmountMinor int64      `json:"amount_minor"`
	Version     int64      `json:"catalog_version"`
	Promotion   *Promotion `json:"promotion,omitempty"`
}

type Source interface {
	Fetch(ctx context.Context, sku, currency string) (Price, error)
}
