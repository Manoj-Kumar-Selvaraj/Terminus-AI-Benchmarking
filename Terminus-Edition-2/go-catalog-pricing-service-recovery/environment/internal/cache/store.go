package cache

import (
	"sync"
	"time"

	"catalog-pricing-service/internal/catalog"
)

type Key struct {
	SKU      string
	Currency string
}

type entry struct {
	price     catalog.Price
	expiresAt time.Time
}

type Store struct {
	mu      sync.RWMutex
	ttl     time.Duration
	now     func() time.Time
	entries map[Key]entry
}

func NewStore(ttl time.Duration, now func() time.Time) *Store {
	if now == nil {
		now = time.Now
	}
	return &Store{
		ttl:     ttl,
		now:     now,
		entries: make(map[Key]entry),
	}
}

func (s *Store) Get(key Key) (catalog.Price, bool) {
	s.mu.RLock()
	item, ok := s.entries[key]
	s.mu.RUnlock()
	if !ok || !s.now().Before(item.expiresAt) {
		if ok {
			s.mu.Lock()
			if current, found := s.entries[key]; found && !s.now().Before(current.expiresAt) {
				delete(s.entries, key)
			}
			s.mu.Unlock()
		}
		return catalog.Price{}, false
	}
	return item.price, true
}

func (s *Store) Set(key Key, price catalog.Price) {
	s.mu.Lock()
	s.entries[key] = entry{price: price, expiresAt: s.now().Add(s.ttl)}
	s.mu.Unlock()
}

func (s *Store) DeleteSKU(sku string) {
	s.mu.Lock()
	for key := range s.entries {
		if key.SKU == sku {
			delete(s.entries, key)
		}
	}
	s.mu.Unlock()
}
