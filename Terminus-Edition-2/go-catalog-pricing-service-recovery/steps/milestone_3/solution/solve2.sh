#!/usr/bin/env bash
set -Eeuo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
bash "$SCRIPT_DIR/solve1.sh"
cat > /app/internal/pricing/service.go <<'GOFILE'
package pricing

import (
    "context"
    "strings"
    "sync"

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

type fillCall struct {
    done   chan struct{}
    result Result
    err    error
}

type Service struct {
    cache  *cache.Store
    source catalog.Source

    stateMu        sync.Mutex
    minimumVersion map[string]int64

    fillMu sync.Mutex
    fills  map[cache.Key]*fillCall
}

func NewService(store *cache.Store, source catalog.Source) *Service {
    return &Service{
        cache:          store,
        source:         source,
        minimumVersion: make(map[string]int64),
        fills:          make(map[cache.Key]*fillCall),
    }
}

func normalizeKey(sku, currency string) cache.Key {
    return cache.Key{SKU: strings.ToUpper(sku), Currency: strings.ToUpper(currency)}
}

func (s *Service) GetPrice(ctx context.Context, sku, currency string) (Result, error) {
    key := normalizeKey(sku, currency)
    if price, ok := s.cache.Get(key); ok {
        return Result{Price: price, CacheStatus: "hit"}, nil
    }

    s.fillMu.Lock()
    if call, ok := s.fills[key]; ok {
        s.fillMu.Unlock()
        select {
        case <-call.done:
            result := call.result
            if call.err == nil && result.CacheStatus == "miss" {
                result.CacheStatus = "shared"
            }
            return result, call.err
        case <-ctx.Done():
            return Result{}, ctx.Err()
        }
    }
    call := &fillCall{done: make(chan struct{})}
    s.fills[key] = call
    s.fillMu.Unlock()

    call.result, call.err = s.fill(ctx, key)

    s.fillMu.Lock()
    delete(s.fills, key)
    close(call.done)
    s.fillMu.Unlock()
    return call.result, call.err
}

func (s *Service) fill(ctx context.Context, key cache.Key) (Result, error) {
    if price, ok := s.cache.Get(key); ok {
        return Result{Price: price, CacheStatus: "hit"}, nil
    }

    price, err := s.source.Fetch(ctx, key.SKU, key.Currency)
    if err != nil {
        return Result{}, err
    }

    s.stateMu.Lock()
    if price.Version >= s.minimumVersion[key.SKU] {
        s.cache.Set(key, price)
    }
    s.stateMu.Unlock()

    return Result{Price: price, CacheStatus: "miss"}, nil
}

func (s *Service) ApplyInvalidation(event Invalidation) {
    sku := strings.ToUpper(event.SKU)
    s.stateMu.Lock()
    if event.MinimumVersion > s.minimumVersion[sku] {
        s.minimumVersion[sku] = event.MinimumVersion
    }
    s.cache.DeleteSKU(sku)
    s.stateMu.Unlock()
}
GOFILE
/usr/local/go/bin/gofmt -w /app/internal/pricing/service.go /app/internal/api/handler.go
