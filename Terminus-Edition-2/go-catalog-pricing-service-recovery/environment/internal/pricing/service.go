package pricing

import (
	"context"
	"strings"

	"catalog-pricing-service/internal/cache"
	"catalog-pricing-service/internal/catalog"
)

type Invalidation struct {
	SKU            string `json:"sku"`
	MinimumVersion int64  `json:"minimum_version"`
}

type Result struct {
	Price       catalog.Price `json:"price"`
	CacheStatus string        `json:"cache_status"`
}

type Service struct {
	cache  *cache.Store
	source catalog.Source
}

func NewService(store *cache.Store, source catalog.Source) *Service {
	return &Service{cache: store, source: source}
}

func normalizeKey(sku, currency string) cache.Key {
	return cache.Key{SKU: strings.ToUpper(sku), Currency: strings.ToUpper(currency)}
}

func (s *Service) GetPrice(ctx context.Context, sku, currency string) (Result, error) {
	key := normalizeKey(sku, currency)
	if price, ok := s.cache.Get(key); ok {
		return Result{Price: price, CacheStatus: "hit"}, nil
	}

	price, err := s.source.Fetch(ctx, key.SKU, key.Currency)
	if err != nil {
		return Result{}, err
	}
	s.cache.Set(key, price)
	return Result{Price: price, CacheStatus: "miss"}, nil
}

func (s *Service) ApplyInvalidation(event Invalidation) {
	s.cache.DeleteSKU(strings.ToUpper(event.SKU))
}
