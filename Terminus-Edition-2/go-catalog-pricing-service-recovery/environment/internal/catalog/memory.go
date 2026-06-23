package catalog

import (
	"context"
	"strings"
	"sync"
)

type MemorySource struct {
	mu     sync.RWMutex
	prices map[string]Price
}

func NewMemorySource(prices []Price) *MemorySource {
	source := &MemorySource{prices: make(map[string]Price)}
	for _, price := range prices {
		source.Set(price)
	}
	return source
}

func memoryKey(sku, currency string) string {
	return strings.ToUpper(sku) + "|" + strings.ToUpper(currency)
}

func (s *MemorySource) Set(price Price) {
	price.SKU = strings.ToUpper(price.SKU)
	price.Currency = strings.ToUpper(price.Currency)
	s.mu.Lock()
	s.prices[memoryKey(price.SKU, price.Currency)] = price
	s.mu.Unlock()
}

func (s *MemorySource) Fetch(_ context.Context, sku, currency string) (Price, error) {
	s.mu.RLock()
	price, ok := s.prices[memoryKey(sku, currency)]
	s.mu.RUnlock()
	if !ok {
		return Price{}, ErrNotFound
	}
	return price, nil
}
