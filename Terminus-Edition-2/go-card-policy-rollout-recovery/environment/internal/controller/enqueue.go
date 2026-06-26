package controller

import (
	"cardrollout/internal/model"
	"cardrollout/internal/store"
	"encoding/json"
	"errors"
	"fmt"
	"sort"
	"strings"
)

func Enqueue(st *store.Store, rolloutID string, generation int64, policy string, regions []string) error {
	rolloutID = strings.TrimSpace(rolloutID)
	if rolloutID == "" {
		return errors.New("rollout id is required")
	}
	if generation <= 0 {
		return errors.New("generation must be positive")
	}
	if !json.Valid([]byte(policy)) {
		return errors.New("policy file must contain valid JSON")
	}
	seen := map[string]bool{}
	clean := make([]string, 0, len(regions))
	for _, region := range regions {
		region = strings.TrimSpace(region)
		if region == "" {
			continue
		}
		if seen[region] {
			return fmt.Errorf("duplicate region %s", region)
		}
		seen[region] = true
		clean = append(clean, region)
	}
	if len(clean) == 0 {
		return errors.New("at least one region is required")
	}
	sort.Strings(clean)
	return st.WithLock(func(state *model.State) error {
		if existing, ok := state.Rollouts[rolloutID]; ok {
			digest := model.PolicyDigest(policy)
			if existing.Generation == generation && existing.PolicySHA256 == digest {
				return nil
			}
			return fmt.Errorf("rollout %s already exists with different content", rolloutID)
		}
		return st.Append(model.Event{
			Version:      2,
			Type:         "queued",
			RolloutID:    rolloutID,
			Generation:   generation,
			Policy:       policy,
			PolicySHA256: model.PolicyDigest(policy),
			Regions:      clean,
		})
	})
}
